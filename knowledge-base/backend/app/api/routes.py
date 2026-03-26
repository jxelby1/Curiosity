from __future__ import annotations

import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.assessment_agent import AssessmentAgent
from app.agents.ingestion_agent import IngestionAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.resource_agent import ResourceAgent
from app.agents.skill_graph_agent import SkillGraphAgent
from app.agents.tutor_agent import TutorAgent
from app.api.auth import CurrentUser
from app.core.course_preferences import (
    assessment_question_count_for_depth,
    normalize_assessment_styles,
    normalize_course_depth,
    normalize_starting_skill_level,
)
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, ProviderError
from app.db.database import get_db
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentFeedback,
    AssessmentQuestion,
    AssessmentQuestionType,
    AssessmentResponse,
    BranchSuggestion,
    Document,
    DocumentChunk,
    ExerciseCompletion,
    LearningResource,
    ResourceType,
    MilestoneEvent,
    Note,
    Recommendation,
    ChatMessage,
    ChatSession,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    TopicInitializationJob,
    UserReminder,
    UserSkillState,
)
from app.schemas.api import (
    AssessmentAttemptResponse,
    AssessmentDetailResponse,
    AssessmentGenerateRequest,
    AssessmentRevealQuestionResponse,
    AssessmentRevealResponse,
    AssessmentQuestionFeedbackResponse,
    AssessmentQuestionResponse,
    AssessmentSubmitRequest,
    AssessmentSubmitResponse,
    ChatRequest,
    ChatResponse,
    AppendTutorResponseToNoteRequest,
    BranchSuggestionGenerateRequest,
    BranchSuggestionListResponse,
    BranchSuggestionResponse,
    SaveTutorResponseToNoteRequest,
    TutorNoteSaveResponse,
    DeepDiveBranchRequest,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    ExerciseCompletionListResponse,
    ExerciseCompletionResponse,
    ExternalResourceItem,
    ExternalResourceResponse,
    GenerateResourceRequest,
    MasteryUpdateRequest,
    MasteryUpdateResponse,
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
    NoteUpdateRequest,
    QuizGenerateRequest,
    QuizResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    RecommendationItem,
    RecommendationResponse,
    ResourceResponse,
    SkillNodeResponse,
    SkillTreeResponse,
    TopicActionItem,
    TopicCreateRequest,
    TopicInitializationResponse,
    TopicInitializationStatusResponse,
    TopicJournalEntryResponse,
    TopicJournalResponse,
    TopicListResponse,
    TopicReminderResponse,
    TopicRetentionLoopResponse,
    TopicProgressNode,
    TopicProgressResponse,
    TopicResponse,
    MilestoneEventResponse,
    UnlockAnticipationResponse,
    UserProgressSummaryResponse,
    UserTopicProgressSummary,
)
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService
from app.services.retention import RetentionService
from app.services.topic_bootstrap import TopicBootstrapService
from app.utils.text import extract_text_from_upload


router = APIRouter()

embedding_service = EmbeddingService()
retrieval_service = RetrievalService(embedding_service)
llm_service = LLMService()
search_service = ExternalSearchService()

skill_graph_agent = SkillGraphAgent(llm_service)
profile_agent = ProfileAgent()
ingestion_agent = IngestionAgent(embedding_service)
tutor_agent = TutorAgent(llm_service, retrieval_service, search_service)
recommendation_agent = RecommendationAgent(llm_service, retrieval_service)
resource_agent = ResourceAgent(llm_service, search_service, retrieval_service)
assessment_agent = AssessmentAgent(llm_service)
retention_service = RetentionService()
topic_bootstrap_service = TopicBootstrapService(
    skill_graph_agent=skill_graph_agent,
    profile_agent=profile_agent,
    recommendation_agent=recommendation_agent,
    resource_agent=resource_agent,
    assessment_agent=assessment_agent,
)
settings = get_settings()


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, ConfigurationError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(exc, ProviderError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _topic_to_response(topic: Topic) -> TopicResponse:
    return TopicResponse(
        id=topic.id,
        user_id=topic.user_id,
        name=topic.name,
        description=topic.description,
        goal=topic.goal,
        course_depth=normalize_course_depth(topic.course_depth),
        starting_skill_level=normalize_starting_skill_level(topic.starting_skill_level),
        assessment_styles=normalize_assessment_styles(topic.allowed_assessment_styles),
        created_at=topic.created_at,
    )


def _document_to_response(document: Document) -> DocumentItemResponse:
    return DocumentItemResponse(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        created_at=document.created_at,
    )


def _topic_init_to_response(job: TopicInitializationJob) -> TopicInitializationStatusResponse:
    status_value = job.status if job.status in {'queued', 'running', 'ready', 'preloading', 'completed', 'failed'} else 'running'
    return TopicInitializationStatusResponse(
        topic_id=job.topic_id,
        status=status_value,  # type: ignore[arg-type]
        current_step=job.current_step or 'Initializing topic',
        progress=round(max(0.0, min(1.0, float(job.progress or 0.0))), 3),
        ready_for_entry=bool(job.ready_for_entry),
        background_complete=bool(job.background_complete),
        first_ready_skill_id=job.first_ready_skill_id,
        status_messages=list(job.status_messages or []),
        error_text=job.error_text or '',
        started_at=job.started_at,
        ready_at=job.ready_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


def _note_to_response(note: Note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        user_id=note.user_id,
        topic_id=note.topic_id,
        skill_node_id=note.skill_node_id,
        note_type=note.note_type,
        tags=note.tags or [],
        source_type=note.source_type,  # type: ignore[arg-type]
        source_chat_session_id=note.source_chat_session_id,
        source_message_id=note.source_message_id,
        created_from_skill_node_id=note.created_from_skill_node_id,
        created_from_topic_id=note.created_from_topic_id,
        title=note.title,
        body=note.body,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _branch_suggestion_to_response(suggestion: BranchSuggestion) -> BranchSuggestionResponse:
    return BranchSuggestionResponse(
        id=suggestion.id,
        topic_id=suggestion.topic_id,
        parent_skill_id=suggestion.parent_skill_id,
        title=suggestion.title,
        focus=suggestion.focus,
        rationale=suggestion.rationale,
        purpose=suggestion.purpose,
        origin=suggestion.origin,
        status=suggestion.status,
        accepted_branch_root_skill_id=suggestion.accepted_branch_root_skill_id,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


def _generate_note_title(body: str) -> str:
    cleaned = body.strip()
    if not cleaned:
        return 'Untitled note'
    first_line = cleaned.splitlines()[0].strip()
    if first_line:
        return first_line[:80]
    words = cleaned.split()
    return ' '.join(words[:10])[:80] or 'Untitled note'


def _get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.scalar(select(Topic).where(Topic.id == topic_id))
    if not topic:
        raise HTTPException(status_code=404, detail='Topic not found')
    return topic


def _get_skill_or_404(db: Session, skill_id: int) -> SkillNode:
    skill = db.scalar(select(SkillNode).where(SkillNode.id == skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail='Skill node not found')
    return skill


def _get_note_or_404(db: Session, note_id: int, user_id: int) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user_id))
    if not note:
        raise HTTPException(status_code=404, detail='Note not found')
    return note


def _get_document_or_404(db: Session, topic_id: int, document_id: int, user_id: int) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.topic_id == topic_id,
            Document.user_id == user_id,
        )
    )
    if not document:
        raise HTTPException(status_code=404, detail='Document not found')
    return document


def _active_generated_resource(
    db: Session,
    *,
    user_id: int,
    skill_node_id: int,
    resource_type: ResourceType,
) -> LearningResource | None:
    return db.scalar(
        select(LearningResource)
        .where(
            LearningResource.user_id == user_id,
            LearningResource.skill_node_id == skill_node_id,
            LearningResource.resource_type == resource_type,
            LearningResource.is_active.is_(True),
        )
        .order_by(LearningResource.version.desc(), LearningResource.created_at.desc())
    )


def _resource_payload(resource: LearningResource | None) -> dict:
    if resource is None:
        return {}
    if isinstance(resource.content_json, dict):
        return resource.content_json
    content = (resource.content or '').strip()
    if not content:
        return {}
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _exercise_items_for_skill(
    db: Session,
    *,
    user_id: int,
    skill_id: int,
) -> tuple[LearningResource | None, list[dict]]:
    resource = _active_generated_resource(
        db,
        user_id=user_id,
        skill_node_id=skill_id,
        resource_type=ResourceType.generated_exercises,
    )
    payload = _resource_payload(resource)
    items_raw = payload.get('exercises')
    if not isinstance(items_raw, list):
        return resource, []
    items: list[dict] = []
    for item in items_raw[:2]:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        task = str(item.get('task') or '').strip()
        if not title or not task:
            continue
        items.append(item)
    return resource, items


def _exercise_completion_to_response(completion: ExerciseCompletion) -> ExerciseCompletionResponse:
    proof_url = f'/api/exercise-completions/{completion.id}/proof' if completion.proof_storage_path else None
    return ExerciseCompletionResponse(
        id=completion.id,
        topic_id=completion.topic_id,
        skill_node_id=completion.skill_node_id,
        resource_id=completion.resource_id,
        exercise_index=completion.exercise_index,
        exercise_title=completion.exercise_title,
        completed_at=completion.completed_at,
        proof_filename=completion.proof_filename,
        proof_content_type=completion.proof_content_type,
        proof_size_bytes=completion.proof_size_bytes,
        proof_url=proof_url,
    )


def _exercise_proof_base_dir() -> Path:
    base = Path(settings.exercise_proof_storage_dir).expanduser()
    if not base.is_absolute():
        base = Path.cwd() / base
    return base


def _exercise_completion_snapshot(
    db: Session,
    *,
    user_id: int,
    skill: SkillNode,
) -> ExerciseCompletionListResponse:
    resource, exercise_items = _exercise_items_for_skill(
        db,
        user_id=user_id,
        skill_id=skill.id,
    )
    title_by_index = {
        idx: str(item.get('title') or f'Exercise {idx + 1}').strip()
        for idx, item in enumerate(exercise_items)
    }
    rows = db.scalars(
        select(ExerciseCompletion)
        .where(
            ExerciseCompletion.user_id == user_id,
            ExerciseCompletion.skill_node_id == skill.id,
        )
        .order_by(ExerciseCompletion.exercise_index.asc(), ExerciseCompletion.completed_at.desc())
    ).all()
    completions: list[ExerciseCompletionResponse] = []
    completed_indexes: set[int] = set()
    for row in rows:
        if row.exercise_index < 0 or row.exercise_index >= max(len(exercise_items), 1):
            continue
        completed_indexes.add(row.exercise_index)
        if title_by_index.get(row.exercise_index) and not row.exercise_title:
            row.exercise_title = title_by_index[row.exercise_index]
        completions.append(_exercise_completion_to_response(row))
    total_exercises = min(2, len(exercise_items))
    completed_count = min(total_exercises, len(completed_indexes))
    completion_ratio = (completed_count / total_exercises) if total_exercises > 0 else 0.0
    if rows:
        db.commit()
    return ExerciseCompletionListResponse(
        skill_node_id=skill.id,
        total_exercises=total_exercises,
        completed_count=completed_count,
        completion_ratio=round(completion_ratio, 3),
        completions=completions,
    )


async def _ensure_assessment_source_material(
    db: Session,
    *,
    user_id: int,
    topic: Topic,
    skill: SkillNode,
) -> None:
    lesson = _active_generated_resource(
        db,
        user_id=user_id,
        skill_node_id=skill.id,
        resource_type=ResourceType.generated_lesson,
    )
    examples = _active_generated_resource(
        db,
        user_id=user_id,
        skill_node_id=skill.id,
        resource_type=ResourceType.generated_examples,
    )
    if lesson and examples:
        return

    if lesson is None:
        await resource_agent.generate_material(
            db,
            user_id=user_id,
            topic=topic,
            skill_node=skill,
            kind='lesson',
            regenerate=False,
        )
    if examples is None:
        await resource_agent.generate_material(
            db,
            user_id=user_id,
            topic=topic,
            skill_node=skill,
            kind='examples',
            regenerate=False,
        )
        profile_agent.record_generated_content(db, user_id, skill, 'examples')


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = tag.strip().lower()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned[:40])
        if len(normalized) >= 12:
            break
    return normalized


def _similarity_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.strip().lower(), right.strip().lower()).ratio()


def _find_duplicate_warning(db: Session, *, user_id: int, topic_id: int, body: str) -> str | None:
    if not body.strip():
        return None
    existing = db.scalars(
        select(Note)
        .where(Note.user_id == user_id, Note.topic_id == topic_id)
        .order_by(Note.updated_at.desc())
        .limit(50)
    ).all()
    best_ratio = 0.0
    for note in existing:
        ratio = _similarity_ratio(note.body, body)
        if ratio > best_ratio:
            best_ratio = ratio
    if best_ratio >= 0.95:
        return 'This content is highly similar to an existing note. Consider updating that note instead.'
    return None


def _get_assistant_message_or_404(
    db: Session,
    *,
    topic_id: int,
    session_id: int,
    message_id: int,
    user_id: int,
) -> tuple[ChatSession, ChatMessage]:
    session = db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.topic_id == topic_id,
            ChatSession.user_id == user_id,
        )
    )
    if not session:
        raise HTTPException(status_code=404, detail='Chat session not found')

    message = db.scalar(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.session_id == session_id,
            ChatMessage.topic_id == topic_id,
            ChatMessage.role == 'assistant',
        )
    )
    if not message:
        raise HTTPException(status_code=404, detail='Tutor response message not found')
    return session, message


async def _generate_tutor_summary_note(
    *,
    topic: Topic,
    tutor_text: str,
    user_prompt: str = '',
) -> str:
    instruction = user_prompt.strip() or 'Summarize this tutor response into a concise study note.'
    summary_prompt = (
        f'Topic: {topic.name}\n'
        f'Instruction: {instruction}\n\n'
        'Summarize the tutor response into a clean learning note with:\n'
        '- a short headline sentence\n'
        '- 3-6 key bullets\n'
        '- one practical next step\n'
        'Keep under 900 characters.\n\n'
        f'Tutor response:\n{tutor_text}'
    )
    summary = await llm_service.generate(
        system_prompt='You are a note-taking assistant. Produce concise, high-signal learning notes.',
        user_prompt=summary_prompt,
        temperature=0.2,
        max_tokens=500,
    )
    return summary.strip()[:4000]


async def _resolve_tutor_note_body(
    *,
    topic: Topic,
    message_text: str,
    mode: str,
    provided_body: str,
) -> str:
    user_body = provided_body.strip()
    if mode == 'full':
        return user_body or message_text.strip()
    if mode == 'excerpt':
        if not user_body:
            raise ValueError('Provide selected excerpt text for excerpt mode.')
        return user_body
    if mode == 'summary':
        if user_body:
            return user_body
        return await _generate_tutor_summary_note(topic=topic, tutor_text=message_text)
    raise ValueError('Invalid save mode.')


async def _reindex_note_document(db: Session, *, note: Note) -> None:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(select(Document.id).where(Document.note_id == note.id))))
    db.execute(delete(Document).where(Document.note_id == note.id))
    db.commit()

    await ingestion_agent.ingest_text(
        db,
        topic_id=note.topic_id,
        user_id=note.user_id,
        note_id=note.id,
        filename=f'note-{note.id}.md',
        content_type='text/markdown',
        text=f'{note.title}\n\n{note.body}',
    )

def _get_or_create_state_for_skill(db: Session, *, user_id: int, skill: SkillNode) -> UserSkillState:
    state = db.scalar(
        select(UserSkillState).where(
            UserSkillState.user_id == user_id,
            UserSkillState.skill_node_id == skill.id,
        )
    )
    if state is None:
        profile_agent.ensure_states_for_topic(db, user_id, skill.topic_id)
        state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_node_id == skill.id,
            )
        )
    if state is None:
        raise HTTPException(status_code=500, detail='Failed to create skill state')
    return state


def _assert_skill_unlocked_for_learning(db: Session, *, user_id: int, skill: SkillNode) -> UserSkillState:
    profile_agent.recompute_unlocks(db, user_id, skill.topic_id)
    state = _get_or_create_state_for_skill(db, user_id=user_id, skill=skill)
    db.refresh(state)
    if state.status == SkillStatus.locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail='Skill node is locked. Verify prerequisite nodes first.',
        )
    return state


def _current_user_can_force_unlock(current_user: CurrentUser) -> bool:
    if not settings.enable_dev_unlocks:
        return False
    if current_user.subscription_tier in {'dev', 'admin'}:
        return True
    if current_user.email.lower() in settings.dev_unlock_email_list:
        return True
    return False


def _build_skill_tree_response(db: Session, topic: Topic, user_id: int) -> SkillTreeResponse:
    nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
    edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all()
    node_map = {node.id: node for node in nodes}

    prereq_map: dict[int, list[int]] = {}
    child_map: dict[int, list[int]] = {}
    for edge in edges:
        if edge.edge_type == 'prerequisite':
            prereq_map.setdefault(edge.child_skill_id, []).append(edge.parent_skill_id)
        child_map.setdefault(edge.parent_skill_id, []).append(edge.child_skill_id)

    state_map: dict[int, UserSkillState] = {}
    for state in db.scalars(
        select(UserSkillState)
        .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
        .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic.id)
    ).all():
        state_map[state.skill_node_id] = state

    payload_nodes: list[SkillNodeResponse] = []
    for node in nodes:
        state = state_map.get(node.id)
        mastery = state.mastery if state else node.mastery_estimate
        node_status = state.status if state else node.status
        if state and state.force_unlocked and node_status == SkillStatus.locked:
            node_status = SkillStatus.available
        progress_state = state.progress_state if state else 'not_started'
        lesson_completed = bool(state.lesson_completed_at) if state else False
        exercises_completed = bool(state.exercises_completed_at) if state else False
        quiz_taken = bool(state.quiz_taken_at) if state else False
        best_quiz_score = round(state.best_quiz_score, 3) if state else None

        action = profile_agent.get_next_requirement(state, node_status)
        lock_reason: str | None = None
        if node_status == SkillStatus.locked:
            missing_prereq_names = [
                node_map[parent_id].name
                for parent_id in prereq_map.get(node.id, [])
                if not state_map.get(parent_id) or state_map[parent_id].progress_state != 'verified'
            ]
            if missing_prereq_names:
                lock_reason = (
                    'Locked until prerequisites are verified: '
                    + ', '.join(missing_prereq_names[:3])
                )
            elif node.branch_parent_skill_id and node.branch_parent_skill_id in node_map:
                lock_reason = f'Optional branch locked until parent node is unlocked: {node_map[node.branch_parent_skill_id].name}'
            else:
                lock_reason = 'Locked until earlier skills are verified.'

        payload_nodes.append(
            SkillNodeResponse(
                id=node.id,
                topic_id=node.topic_id,
                name=node.name,
                description=node.description,
                difficulty=node.difficulty,
                node_kind=node.node_kind,  # type: ignore[arg-type]
                branch_origin=node.branch_origin,
                branch_purpose=node.branch_purpose,
                branch_depth=node.branch_depth,
                branch_parent_skill_id=node.branch_parent_skill_id,
                mastery_estimate=round(float(mastery), 3),
                status=node_status,
                force_unlocked=bool(state.force_unlocked) if state else False,
                lock_reason=lock_reason,
                progress_state=progress_state,  # type: ignore[arg-type]
                lesson_completed=lesson_completed,
                exercises_completed=exercises_completed,
                quiz_taken=quiz_taken,
                best_quiz_score=best_quiz_score,
                prerequisites=prereq_map.get(node.id, []),
                children=child_map.get(node.id, []),
                recommended_next_action=action,
            )
        )

    payload_nodes.sort(key=lambda item: (0 if item.node_kind == 'core' else 1, item.difficulty, item.id))
    return SkillTreeResponse(topic=_topic_to_response(topic), nodes=payload_nodes)


def _invalidate_recommendations(db: Session, topic_id: int, user_id: int) -> None:
    db.execute(delete(Recommendation).where(Recommendation.topic_id == topic_id, Recommendation.user_id == user_id))
    db.commit()


def _collect_unlocked_skill_ids(db: Session, *, topic_id: int, user_id: int) -> set[int]:
    rows = db.scalars(
        select(UserSkillState)
        .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
        .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic_id)
    ).all()
    return {row.skill_node_id for row in rows if row.status != SkillStatus.locked}


def _topic_tree_stage(
    *,
    total_nodes: int,
    verified_nodes: int,
    available_nodes: int,
    mastery_average: float,
) -> int:
    if total_nodes <= 0:
        return 1

    verified_ratio = verified_nodes / total_nodes
    unlocked_ratio = available_nodes / total_nodes
    mastery_ratio = max(0.0, min(1.0, mastery_average))

    growth_score = (0.45 * mastery_ratio) + (0.35 * verified_ratio) + (0.20 * unlocked_ratio)
    stage = int(growth_score * 5) + 1
    return max(1, min(6, stage))


def _ensure_topic_milestone_events(db: Session, *, topic: Topic, user_id: int) -> None:
    tree = _build_skill_tree_response(db, topic, user_id)
    total_nodes = len(tree.nodes)
    verified_nodes = sum(1 for node in tree.nodes if node.progress_state == 'verified')
    available_nodes = sum(1 for node in tree.nodes if node.status != SkillStatus.locked)
    mastery_average = round(mean(node.mastery_estimate for node in tree.nodes), 3) if tree.nodes else 0.0
    tree_stage = _topic_tree_stage(
        total_nodes=total_nodes,
        verified_nodes=verified_nodes,
        available_nodes=available_nodes,
        mastery_average=mastery_average,
    )

    nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
    states = db.scalars(
        select(UserSkillState)
        .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
        .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic.id)
    ).all()
    retention_service.ensure_topic_milestones(
        db,
        topic=topic,
        user_id=user_id,
        nodes=nodes,
        state_map={state.skill_node_id: state for state in states},
        tree_stage=tree_stage,
    )


def _action_to_response(action: object) -> TopicActionItem:
    tab_value = str(getattr(action, 'tab', 'overview') or 'overview')
    if tab_value not in {'overview', 'lesson', 'examples', 'exercises', 'quiz', 'resources'}:
        tab_value = 'overview'
    return TopicActionItem(
        skill_node_id=getattr(action, 'skill_node_id', None),
        skill_name=str(getattr(action, 'skill_name', '')),
        action_type=str(getattr(action, 'action_type', 'action')),
        title=str(getattr(action, 'title', 'Continue learning')),
        description=str(getattr(action, 'description', '')),
        tab=tab_value,  # type: ignore[arg-type]
    )


def _unlock_to_response(unlock: object | None) -> UnlockAnticipationResponse | None:
    if unlock is None:
        return None
    tab_value = str(getattr(unlock, 'next_step_tab', 'overview') or 'overview')
    if tab_value not in {'overview', 'lesson', 'examples', 'exercises', 'quiz', 'resources'}:
        tab_value = 'overview'
    return UnlockAnticipationResponse(
        skill_node_id=int(getattr(unlock, 'skill_node_id')),
        skill_name=str(getattr(unlock, 'skill_name', '')),
        status_label=str(getattr(unlock, 'status_label', 'Coming soon')),
        why_locked=str(getattr(unlock, 'why_locked', 'Complete prerequisites to unlock this skill.')),
        steps=[str(item) for item in list(getattr(unlock, 'steps', []) or [])],
        next_step_skill_node_id=getattr(unlock, 'next_step_skill_node_id', None),
        next_step_tab=tab_value,  # type: ignore[arg-type]
    )


def _reminder_to_response(reminder: UserReminder | None) -> TopicReminderResponse | None:
    if reminder is None:
        return None
    tab_value = reminder.action_tab or 'overview'
    if tab_value not in {'overview', 'lesson', 'examples', 'exercises', 'quiz', 'resources'}:
        tab_value = 'overview'
    return TopicReminderResponse(
        id=reminder.id,
        reminder_type=reminder.reminder_type,
        title=reminder.title,
        message=reminder.message,
        action_skill_node_id=reminder.action_skill_node_id,
        action_tab=tab_value,  # type: ignore[arg-type]
        created_at=reminder.created_at,
    )


def _milestone_to_response(event: MilestoneEvent) -> MilestoneEventResponse:
    return MilestoneEventResponse(
        id=event.id,
        milestone_type=event.milestone_type,
        title=event.title,
        message=event.message,
        skill_node_id=event.skill_node_id,
        created_at=event.created_at,
    )


def _topic_journal_response(db: Session, *, topic: Topic, user_id: int) -> TopicJournalResponse:
    skill_map = {
        node.id: node.name
        for node in db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
    }
    entries: list[TopicJournalEntryResponse] = []

    notes = db.scalars(
        select(Note)
        .where(Note.topic_id == topic.id, Note.user_id == user_id)
        .order_by(Note.updated_at.desc())
        .limit(160)
    ).all()
    for note in notes:
        snippet = (note.body or '').strip().replace('\n', ' ')
        snippet = snippet[:180] + ('…' if len(snippet) > 180 else '')
        entries.append(
            TopicJournalEntryResponse(
                id=f'note-{note.id}',
                entry_type='note',
                title=note.title or 'Untitled note',
                description=snippet or 'Personal note updated.',
                skill_node_id=note.skill_node_id,
                skill_name=skill_map.get(note.skill_node_id) if note.skill_node_id else None,
                occurred_at=note.updated_at,
                metadata={
                    'note_type': note.note_type.value,
                    'source_type': note.source_type,
                    'tags': note.tags or [],
                },
            )
        )

    exercise_completions = db.scalars(
        select(ExerciseCompletion)
        .where(
            ExerciseCompletion.topic_id == topic.id,
            ExerciseCompletion.user_id == user_id,
        )
        .order_by(ExerciseCompletion.completed_at.desc())
        .limit(160)
    ).all()
    for completion in exercise_completions:
        has_proof = bool(completion.proof_storage_path)
        entries.append(
            TopicJournalEntryResponse(
                id=f'exercise-{completion.id}',
                entry_type='exercise',
                title=f'Completed exercise {completion.exercise_index + 1}: {completion.exercise_title}',
                description=(
                    'Exercise completion recorded with proof artifact.'
                    if has_proof
                    else 'Exercise completion recorded.'
                ),
                skill_node_id=completion.skill_node_id,
                skill_name=skill_map.get(completion.skill_node_id),
                occurred_at=completion.completed_at,
                metadata={
                    'exercise_index': completion.exercise_index,
                    'proof_uploaded': has_proof,
                    'proof_filename': completion.proof_filename,
                    'proof_url': f'/api/exercise-completions/{completion.id}/proof' if has_proof else None,
                },
            )
        )

    states = db.scalars(
        select(UserSkillState)
        .join(SkillNode, UserSkillState.skill_node_id == SkillNode.id)
        .where(UserSkillState.user_id == user_id, SkillNode.topic_id == topic.id)
    ).all()
    for state in states:
        skill_name = skill_map.get(state.skill_node_id)
        if state.lesson_completed_at:
            entries.append(
                TopicJournalEntryResponse(
                    id=f'module-lesson-{state.skill_node_id}',
                    entry_type='module',
                    title=f'Lesson completed: {skill_name or "Skill"}',
                    description='You completed the lesson content for this node.',
                    skill_node_id=state.skill_node_id,
                    skill_name=skill_name,
                    occurred_at=state.lesson_completed_at,
                    metadata={'event': 'lesson_completed'},
                )
            )
        if state.exercises_completed_at:
            entries.append(
                TopicJournalEntryResponse(
                    id=f'module-exercises-{state.skill_node_id}',
                    entry_type='module',
                    title=f'Exercise milestone reached: {skill_name or "Skill"}',
                    description='You completed at least one exercise for this node.',
                    skill_node_id=state.skill_node_id,
                    skill_name=skill_name,
                    occurred_at=state.exercises_completed_at,
                    metadata={'event': 'exercise_progress'},
                )
            )
        if state.quiz_taken_at:
            entries.append(
                TopicJournalEntryResponse(
                    id=f'module-assessment-{state.skill_node_id}',
                    entry_type='module',
                    title=f'Assessment attempted: {skill_name or "Skill"}',
                    description='Assessment activity was recorded for this node.',
                    skill_node_id=state.skill_node_id,
                    skill_name=skill_name,
                    occurred_at=state.quiz_taken_at,
                    metadata={'event': 'assessment_activity'},
                )
            )

    assessment_ids = db.scalars(
        select(Assessment.id).where(Assessment.topic_id == topic.id, Assessment.user_id == user_id)
    ).all()
    if assessment_ids:
        attempts = db.scalars(
            select(AssessmentAttempt)
            .where(AssessmentAttempt.assessment_id.in_(assessment_ids))
            .order_by(AssessmentAttempt.created_at.desc())
            .limit(160)
        ).all()
        assessment_skill_map = {
            row.id: row.skill_node_id
            for row in db.scalars(select(Assessment).where(Assessment.id.in_(assessment_ids))).all()
        }
        for attempt in attempts:
            skill_id = assessment_skill_map.get(attempt.assessment_id)
            score_pct = int(round(float(attempt.score or 0.0) * 100))
            mode_label = 'Practice mode' if attempt.practice_mode else 'Mastery attempt'
            entries.append(
                TopicJournalEntryResponse(
                    id=f'assessment-attempt-{attempt.id}',
                    entry_type='assessment',
                    title=f'Assessment result: {score_pct}% ({mode_label})',
                    description=(attempt.review_next or '').strip()[:220] or 'Assessment feedback recorded.',
                    skill_node_id=skill_id,
                    skill_name=skill_map.get(skill_id) if skill_id else None,
                    occurred_at=attempt.created_at,
                    metadata={
                        'score': round(float(attempt.score or 0.0), 3),
                        'practice_mode': bool(attempt.practice_mode),
                        'mastery_eligible': bool(attempt.mastery_eligible),
                    },
                )
            )

    milestones = db.scalars(
        select(MilestoneEvent)
        .where(MilestoneEvent.topic_id == topic.id, MilestoneEvent.user_id == user_id)
        .order_by(MilestoneEvent.created_at.desc())
        .limit(80)
    ).all()
    for milestone in milestones:
        entries.append(
            TopicJournalEntryResponse(
                id=f'milestone-{milestone.id}',
                entry_type='milestone',
                title=milestone.title,
                description=milestone.message,
                skill_node_id=milestone.skill_node_id,
                skill_name=skill_map.get(milestone.skill_node_id) if milestone.skill_node_id else None,
                occurred_at=milestone.created_at,
                metadata={
                    'milestone_type': milestone.milestone_type,
                },
            )
        )

    entries.sort(key=lambda item: item.occurred_at, reverse=True)
    return TopicJournalResponse(
        topic_id=topic.id,
        topic_name=topic.name,
        entries=entries[:240],
    )


def _assessment_to_response(
    db: Session,
    *,
    assessment: Assessment,
    source: str = 'stored',
) -> AssessmentDetailResponse:
    rows = db.scalars(
        select(AssessmentQuestion)
        .where(AssessmentQuestion.assessment_id == assessment.id)
        .order_by(AssessmentQuestion.order_index.asc())
    ).all()
    questions = [
        AssessmentQuestionResponse(
            id=row.id,
            question_type=row.question_type,
            assessment_style=row.assessment_style or 'short_answer',
            prompt=row.prompt,
            choices=row.choices or [],
            expected_concepts=row.expected_concepts or [],
            rubric=row.rubric or {},
            difficulty=row.difficulty,
            order_index=row.order_index,
        )
        for row in rows
    ]
    return AssessmentDetailResponse(
        id=assessment.id,
        topic_id=assessment.topic_id,
        skill_node_id=assessment.skill_node_id,
        title=assessment.title,
        difficulty=assessment.difficulty,
        target_level=assessment.target_level,
        question_mix=assessment.question_mix or {},
        version=assessment.version,
        source=source,  # type: ignore[arg-type]
        answers_revealed=bool(assessment.answers_revealed),
        mastery_eligible=not bool(assessment.answers_revealed),
        questions=questions,
        created_at=assessment.created_at,
    )


def _attempt_to_response(db: Session, *, attempt: AssessmentAttempt) -> AssessmentAttemptResponse:
    rows = db.scalars(
        select(AssessmentResponse)
        .where(AssessmentResponse.attempt_id == attempt.id)
        .order_by(AssessmentResponse.id.asc())
    ).all()
    question_map = {
        row.id: row
        for row in db.scalars(
            select(AssessmentQuestion).where(
                AssessmentQuestion.id.in_([item.question_id for item in rows])  # type: ignore[arg-type]
            )
        ).all()
    }

    feedback_items = [
        AssessmentQuestionFeedbackResponse(
            question_id=row.question_id,
            question_type=question_map[row.question_id].question_type
            if row.question_id in question_map
            else AssessmentQuestionType.short_answer,
            assessment_style=question_map[row.question_id].assessment_style if row.question_id in question_map else 'short_answer',
            score=(
                None
                if row.question_id in question_map
                and question_map[row.question_id].question_type == AssessmentQuestionType.reflection
                else round(row.score, 3)
            ),
            confidence_score=round(row.confidence_score, 3) if row.confidence_score is not None else None,
            feedback=row.feedback,
            missing_concepts=[],
        )
        for row in rows
    ]

    return AssessmentAttemptResponse(
        id=attempt.id,
        assessment_id=attempt.assessment_id,
        user_id=attempt.user_id,
        score=round(attempt.score, 3),
        confidence_avg=round(attempt.confidence_avg, 3),
        mastery_delta=round(attempt.mastery_delta, 3),
        mastery_eligible=attempt.mastery_eligible is not False,
        practice_mode=bool(attempt.practice_mode),
        strengths=attempt.strengths or [],
        weaknesses=attempt.weaknesses or [],
        review_next=attempt.review_next,
        recommended_follow_up=attempt.recommended_follow_up,
        feedback=feedback_items,
        created_at=attempt.created_at,
    )


@router.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/topics', response_model=TopicListResponse)
def list_topics(current_user: CurrentUser, db: Session = Depends(get_db)) -> TopicListResponse:
    topics = db.scalars(
        select(Topic).where(Topic.user_id == current_user.id).order_by(Topic.created_at.desc())
    ).all()
    return TopicListResponse(topics=[_topic_to_response(topic) for topic in topics])


@router.post('/topics', response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(
    payload: TopicCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TopicResponse:

    topic = Topic(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        goal=payload.goal.strip(),
        course_depth=normalize_course_depth(payload.course_depth),
        starting_skill_level=normalize_starting_skill_level(payload.starting_skill_level),
        allowed_assessment_styles=normalize_assessment_styles(payload.assessment_styles),
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    try:
        await skill_graph_agent.create_skill_tree(db, topic)
    except Exception as exc:  # noqa: BLE001
        db.delete(topic)
        db.commit()
        _raise_service_error(exc)

    profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
    return _topic_to_response(topic)


@router.post(
    '/topics/create-and-initialize',
    response_model=TopicInitializationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_topic_and_initialize(
    payload: TopicCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TopicInitializationResponse:
    topic = Topic(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        goal=payload.goal.strip(),
        course_depth=normalize_course_depth(payload.course_depth),
        starting_skill_level=normalize_starting_skill_level(payload.starting_skill_level),
        allowed_assessment_styles=normalize_assessment_styles(payload.assessment_styles),
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    try:
        job = await topic_bootstrap_service.start_initialization(
            db,
            topic=topic,
            user_id=current_user.id,
            force=True,
        )
    except Exception as exc:  # noqa: BLE001
        db.delete(topic)
        db.commit()
        _raise_service_error(exc)

    return TopicInitializationResponse(
        topic=_topic_to_response(topic),
        initialization=_topic_init_to_response(job),
    )


@router.post('/topics/{topic_id}/initialize', response_model=TopicInitializationStatusResponse)
async def initialize_topic(
    topic_id: int,
    current_user: CurrentUser,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> TopicInitializationStatusResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    try:
        job = await topic_bootstrap_service.start_initialization(
            db,
            topic=topic,
            user_id=current_user.id,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return _topic_init_to_response(job)


@router.get('/topics/{topic_id}/initialization-status', response_model=TopicInitializationStatusResponse)
def get_topic_initialization_status(
    topic_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TopicInitializationStatusResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    job = db.scalar(
        select(TopicInitializationJob).where(
            TopicInitializationJob.topic_id == topic_id,
            TopicInitializationJob.user_id == current_user.id,
        )
    )
    if not job:
        raise HTTPException(
            status_code=404,
            detail='No initialization job found for this topic. Start initialization first.',
        )
    return _topic_init_to_response(job)


@router.delete('/topics/{topic_id}', status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_topic(
    topic_id: int,
    current_user: CurrentUser,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Response:
    topic = _get_topic_or_404(db, topic_id)

    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    if not confirm:
        raise HTTPException(status_code=400, detail='Set confirm=true to delete this topic.')

    skill_ids = db.scalars(select(SkillNode.id).where(SkillNode.topic_id == topic_id)).all()

    assessment_ids_subquery = select(Assessment.id).where(
        Assessment.topic_id == topic_id,
        Assessment.user_id == current_user.id,
    )
    assessment_attempt_ids_subquery = select(AssessmentAttempt.id).where(
        AssessmentAttempt.assessment_id.in_(assessment_ids_subquery)
    )
    assessment_question_ids_subquery = select(AssessmentQuestion.id).where(
        AssessmentQuestion.assessment_id.in_(assessment_ids_subquery)
    )

    # Delete assessment children first to avoid FK violations on assessment removal.
    db.execute(delete(AssessmentFeedback).where(AssessmentFeedback.attempt_id.in_(assessment_attempt_ids_subquery)))
    db.execute(delete(AssessmentResponse).where(AssessmentResponse.attempt_id.in_(assessment_attempt_ids_subquery)))
    db.execute(delete(AssessmentResponse).where(AssessmentResponse.question_id.in_(assessment_question_ids_subquery)))
    db.execute(delete(AssessmentAttempt).where(AssessmentAttempt.id.in_(assessment_attempt_ids_subquery)))
    db.execute(delete(AssessmentQuestion).where(AssessmentQuestion.id.in_(assessment_question_ids_subquery)))

    db.execute(delete(ChatMessage).where(ChatMessage.topic_id == topic_id))
    db.execute(delete(ChatSession).where(ChatSession.topic_id == topic_id))
    db.execute(
        delete(Recommendation).where(Recommendation.topic_id == topic_id, Recommendation.user_id == current_user.id)
    )
    db.execute(
        delete(BranchSuggestion).where(
            BranchSuggestion.topic_id == topic_id,
            BranchSuggestion.user_id == current_user.id,
        )
    )
    db.execute(delete(UserReminder).where(UserReminder.topic_id == topic_id, UserReminder.user_id == current_user.id))
    db.execute(delete(MilestoneEvent).where(MilestoneEvent.topic_id == topic_id, MilestoneEvent.user_id == current_user.id))
    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id.in_(select(Document.id).where(Document.topic_id == topic_id, Document.user_id == current_user.id))
        )
    )
    db.execute(delete(Document).where(Document.topic_id == topic_id, Document.user_id == current_user.id))
    db.execute(delete(Note).where(Note.topic_id == topic_id, Note.user_id == current_user.id))
    exercise_completions = db.scalars(
        select(ExerciseCompletion).where(
            ExerciseCompletion.topic_id == topic_id,
            ExerciseCompletion.user_id == current_user.id,
        )
    ).all()
    for completion in exercise_completions:
        if completion.proof_storage_path:
            proof_path = Path(completion.proof_storage_path)
            if proof_path.exists():
                proof_path.unlink(missing_ok=True)
    db.execute(delete(ExerciseCompletion).where(ExerciseCompletion.topic_id == topic_id, ExerciseCompletion.user_id == current_user.id))
    db.execute(delete(LearningResource).where(LearningResource.topic_id == topic_id))
    db.execute(delete(Assessment).where(Assessment.id.in_(assessment_ids_subquery)))
    db.execute(
        delete(TopicInitializationJob).where(
            TopicInitializationJob.topic_id == topic_id,
            TopicInitializationJob.user_id == current_user.id,
        )
    )
    db.execute(delete(SkillEdge).where(SkillEdge.topic_id == topic_id))
    if skill_ids:
        db.execute(
            delete(UserSkillState).where(
                UserSkillState.user_id == current_user.id, UserSkillState.skill_node_id.in_(skill_ids)
            )
        )
    db.execute(delete(SkillNode).where(SkillNode.topic_id == topic_id))
    db.delete(topic)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/topics/{topic_id}/skill-tree/generate', response_model=SkillTreeResponse)
async def generate_skill_tree(
    topic_id: int,
    current_user: CurrentUser,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> SkillTreeResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    existing = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
    if existing and not regenerate:
        profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
        profile_agent.recompute_unlocks(db, current_user.id, topic.id)
        return _build_skill_tree_response(db, topic, current_user.id)

    if existing and regenerate:
        db.execute(delete(SkillEdge).where(SkillEdge.topic_id == topic.id))
        db.execute(delete(SkillNode).where(SkillNode.topic_id == topic.id))
        db.commit()

    try:
        await skill_graph_agent.create_skill_tree(db, topic)
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
    profile_agent.recompute_unlocks(db, current_user.id, topic.id)
    return _build_skill_tree_response(db, topic, current_user.id)


@router.get('/topics/{topic_id}/skill-tree', response_model=SkillTreeResponse)
def get_skill_tree(topic_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> SkillTreeResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    profile_agent.ensure_states_for_topic(db, current_user.id, topic_id)
    profile_agent.recompute_unlocks(db, current_user.id, topic_id)
    return _build_skill_tree_response(db, topic, current_user.id)


@router.post('/topics/{topic_id}/documents/upload', response_model=DocumentUploadResponse)
@router.post('/topics/{topic_id}/notes/upload', response_model=DocumentUploadResponse)
async def upload_document(
    topic_id: int,
    current_user: CurrentUser,
    raw_text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    text = (raw_text or '').strip()
    filename = f'pasted-source-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.txt'
    content_type = 'text/plain'

    if file is not None:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail='Uploaded file is empty')
        try:
            text = extract_text_from_upload(file.content_type or '', file.filename or 'upload.txt', data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filename = file.filename or 'upload.txt'
        content_type = file.content_type or 'application/octet-stream'

    if not text:
        raise HTTPException(status_code=400, detail='Provide either raw_text or an uploaded file')

    try:
        doc, chunks = await ingestion_agent.ingest_text(
            db,
            topic_id=topic_id,
            user_id=current_user.id,
            filename=filename,
            content_type=content_type,
            text=text,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.infer_mastery_from_notes(db, current_user.id, topic_id)
    _invalidate_recommendations(db, topic_id, current_user.id)

    return DocumentUploadResponse(document_id=doc.id, filename=doc.filename, chunks_created=chunks)


@router.get('/topics/{topic_id}/documents', response_model=DocumentListResponse)
def list_documents(topic_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> DocumentListResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    docs = db.scalars(
        select(Document)
        .where(Document.topic_id == topic_id, Document.user_id == current_user.id, Document.note_id.is_(None))
        .order_by(Document.created_at.desc())
    ).all()

    return DocumentListResponse(documents=[_document_to_response(doc) for doc in docs])


@router.delete(
    '/topics/{topic_id}/documents/{document_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_document(
    topic_id: int,
    document_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    document = _get_document_or_404(db, topic_id, document_id, current_user.id)
    if document.note_id is not None:
        raise HTTPException(status_code=400, detail='This document is linked to a note and cannot be deleted here.')

    db.delete(document)
    db.commit()
    profile_agent.infer_mastery_from_notes(db, current_user.id, topic_id)
    _invalidate_recommendations(db, topic_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/topics/{topic_id}/notes', response_model=NoteListResponse)
def list_notes(
    topic_id: int,
    current_user: CurrentUser,
    skill_node_id: int | None = Query(default=None),
    query: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> NoteListResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    stmt = select(Note).where(Note.topic_id == topic_id, Note.user_id == current_user.id)
    if skill_node_id is not None:
        stmt = stmt.where(Note.skill_node_id == skill_node_id)
    if query:
        pattern = f'%{query.strip()}%'
        if pattern != '%%':
            stmt = stmt.where((Note.title.ilike(pattern)) | (Note.body.ilike(pattern)))
    notes = db.scalars(stmt.order_by(Note.updated_at.desc())).all()

    return NoteListResponse(notes=[_note_to_response(note) for note in notes])


@router.get('/topics/{topic_id}/journal', response_model=TopicJournalResponse)
def get_topic_journal(
    topic_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TopicJournalResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    profile_agent.ensure_states_for_topic(db, current_user.id, topic_id)
    return _topic_journal_response(db, topic=topic, user_id=current_user.id)


@router.post('/topics/{topic_id}/notes', response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    topic_id: int,
    payload: NoteCreateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> NoteResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail='Note body cannot be empty')

    if payload.skill_node_id is not None:
        skill = _get_skill_or_404(db, payload.skill_node_id)
        if skill.topic_id != topic_id:
            raise HTTPException(status_code=400, detail='skill_node_id does not belong to this topic')

    title = payload.title.strip() or _generate_note_title(body)
    note = Note(
        user_id=current_user.id,
        topic_id=topic_id,
        skill_node_id=payload.skill_node_id,
        note_type=payload.note_type,
        tags=_normalize_tags(payload.tags),
        source_type='user_authored',
        source_chat_session_id=None,
        source_message_id=None,
        created_from_skill_node_id=payload.skill_node_id,
        created_from_topic_id=topic_id,
        title=title,
        body=body,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_to_response(note)


@router.get('/notes/{note_id}', response_model=NoteResponse)
def get_note(note_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> NoteResponse:
    note = _get_note_or_404(db, note_id, current_user.id)
    return _note_to_response(note)


@router.put('/notes/{note_id}', response_model=NoteResponse)
async def update_note(
    note_id: int,
    payload: NoteUpdateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> NoteResponse:
    note = _get_note_or_404(db, note_id, current_user.id)

    if 'skill_node_id' in payload.model_fields_set and payload.skill_node_id is not None:
        skill = _get_skill_or_404(db, payload.skill_node_id)
        if skill.topic_id != note.topic_id:
            raise HTTPException(status_code=400, detail='skill_node_id does not belong to this topic')

    had_indexed_document = db.scalar(select(Document.id).where(Document.note_id == note.id).limit(1)) is not None
    content_changed = False

    if payload.title is not None:
        note.title = payload.title.strip() or _generate_note_title(payload.body or note.body)
        content_changed = True
    if payload.body is not None:
        body = payload.body.strip()
        if not body:
            raise HTTPException(status_code=400, detail='Note body cannot be empty')
        note.body = body
        content_changed = True
        if payload.title is None and not note.title.strip():
            note.title = _generate_note_title(body)
    if payload.note_type is not None:
        note.note_type = payload.note_type
    if payload.tags is not None:
        note.tags = _normalize_tags(payload.tags)

    if 'skill_node_id' in payload.model_fields_set:
        note.skill_node_id = payload.skill_node_id
    note.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(note)
    if had_indexed_document and content_changed:
        await _reindex_note_document(db, note=note)
        db.refresh(note)
    return _note_to_response(note)


@router.delete('/notes/{note_id}', status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_note(note_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> Response:
    note = _get_note_or_404(db, note_id, current_user.id)
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(select(Document.id).where(Document.note_id == note.id))))
    db.execute(delete(Document).where(Document.note_id == note.id))
    db.delete(note)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/topics/{topic_id}/chat', response_model=ChatResponse)
async def chat(
    topic_id: int,
    payload: ChatRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ChatResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    try:
        session_id, assistant_message_id, answer, used_chunks, structured_answer, context_usage, citations = await tutor_agent.respond(
            db,
            topic=topic,
            user_id=current_user.id,
            message=payload.message,
            session_id=payload.session_id,
            skill_node_id=payload.skill_node_id,
            include_personal_notes=payload.include_personal_notes,
            include_web_resources=payload.include_web_resources,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return ChatResponse(
        session_id=session_id,
        assistant_message_id=assistant_message_id,
        answer=answer,
        used_chunks=used_chunks,
        citations=citations,
        structured_answer=structured_answer,
        context_usage=context_usage,
    )


@router.post(
    '/topics/{topic_id}/chat/{session_id}/messages/{message_id}/save-note',
    response_model=TutorNoteSaveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_tutor_response_to_note(
    topic_id: int,
    session_id: int,
    message_id: int,
    payload: SaveTutorResponseToNoteRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TutorNoteSaveResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    session, message = _get_assistant_message_or_404(
        db,
        topic_id=topic_id,
        session_id=session_id,
        message_id=message_id,
        user_id=current_user.id,
    )

    existing = db.scalar(
        select(Note).where(
            Note.user_id == current_user.id,
            Note.topic_id == topic_id,
            Note.source_type == 'tutor_generated',
            Note.source_message_id == message.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail='This tutor response is already saved to notes.')

    try:
        resolved_body = await _resolve_tutor_note_body(
            topic=topic,
            message_text=message.content,
            mode=payload.mode,
            provided_body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    duplicate_warning = _find_duplicate_warning(
        db,
        user_id=current_user.id,
        topic_id=topic_id,
        body=resolved_body,
    )
    target_skill_id = payload.skill_node_id if payload.skill_node_id is not None else message.skill_node_id
    if target_skill_id is not None:
        skill = _get_skill_or_404(db, target_skill_id)
        if skill.topic_id != topic_id:
            raise HTTPException(status_code=400, detail='skill_node_id does not belong to this topic')

    note = Note(
        user_id=current_user.id,
        topic_id=topic_id,
        skill_node_id=target_skill_id,
        note_type=payload.note_type,
        tags=_normalize_tags(payload.tags),
        source_type='tutor_generated',
        source_chat_session_id=session.id,
        source_message_id=message.id,
        created_from_skill_node_id=target_skill_id,
        created_from_topic_id=topic_id,
        title=payload.title.strip() or _generate_note_title(resolved_body),
        body=resolved_body.strip(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    await _reindex_note_document(db, note=note)
    profile_agent.infer_mastery_from_notes(db, current_user.id, topic_id)
    _invalidate_recommendations(db, topic_id, current_user.id)

    return TutorNoteSaveResponse(
        note=_note_to_response(note),
        duplicate_warning=duplicate_warning,
        appended=False,
    )


@router.post('/notes/{note_id}/append-tutor-response', response_model=TutorNoteSaveResponse)
async def append_tutor_response_to_existing_note(
    note_id: int,
    payload: AppendTutorResponseToNoteRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TutorNoteSaveResponse:
    note = _get_note_or_404(db, note_id, current_user.id)
    topic = _get_topic_or_404(db, note.topic_id)

    _session, message = _get_assistant_message_or_404(
        db,
        topic_id=note.topic_id,
        session_id=payload.session_id,
        message_id=payload.message_id,
        user_id=current_user.id,
    )

    try:
        append_body = await _resolve_tutor_note_body(
            topic=topic,
            message_text=message.content,
            mode=payload.mode,
            provided_body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    append_clean = append_body.strip()
    if not append_clean:
        raise HTTPException(status_code=400, detail='Resolved tutor content is empty.')

    if append_clean.lower() in note.body.lower():
        return TutorNoteSaveResponse(
            note=_note_to_response(note),
            duplicate_warning='This content already exists in the selected note.',
            appended=False,
        )

    note.body = f'{note.body.rstrip()}\n\n---\n\n{append_clean}'.strip()
    note.updated_at = datetime.utcnow()
    note.tags = _normalize_tags((note.tags or []) + payload.tags)
    if note.source_type != 'tutor_generated':
        note.source_type = 'tutor_generated'
    note.source_chat_session_id = payload.session_id
    note.source_message_id = payload.message_id
    note.created_from_skill_node_id = note.skill_node_id or message.skill_node_id
    note.created_from_topic_id = note.topic_id

    duplicate_warning = _find_duplicate_warning(
        db,
        user_id=current_user.id,
        topic_id=note.topic_id,
        body=append_clean,
    )

    db.commit()
    db.refresh(note)
    await _reindex_note_document(db, note=note)
    profile_agent.infer_mastery_from_notes(db, current_user.id, note.topic_id)
    _invalidate_recommendations(db, note.topic_id, current_user.id)

    return TutorNoteSaveResponse(
        note=_note_to_response(note),
        duplicate_warning=duplicate_warning,
        appended=True,
    )


@router.get('/topics/{topic_id}/recommendations', response_model=RecommendationResponse)
async def get_recommendations(
    topic_id: int,
    current_user: CurrentUser,
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    profile_agent.ensure_states_for_topic(db, current_user.id, topic_id)
    profile_agent.recompute_unlocks(db, current_user.id, topic_id)

    records: list[Recommendation]
    if not refresh:
        freshness_cutoff = datetime.utcnow() - timedelta(minutes=3)
        cached = db.scalars(
            select(Recommendation)
            .where(Recommendation.topic_id == topic_id, Recommendation.user_id == current_user.id)
            .order_by(Recommendation.created_at.desc())
        ).all()
        if cached and cached[0].created_at >= freshness_cutoff:
            records = cached
        else:
            try:
                records = await recommendation_agent.generate_recommendations(db, topic, current_user.id)
            except Exception as exc:  # noqa: BLE001
                _raise_service_error(exc)
    else:
        try:
            records = await recommendation_agent.generate_recommendations(db, topic, current_user.id)
        except Exception as exc:  # noqa: BLE001
            _raise_service_error(exc)

    node_map = {node.id: node for node in db.scalars(select(SkillNode).where(SkillNode.topic_id == topic_id)).all()}

    payload: list[RecommendationItem] = []
    for rec in records:
        resource_mode = 'external' if rec.action_type == 'study_external' else 'generated'
        payload.append(
            RecommendationItem(
                skill_node_id=rec.skill_node_id,
                skill_name=node_map[rec.skill_node_id].name if rec.skill_node_id in node_map else 'Unknown node',
                rationale=rec.rationale,
                action_type=rec.action_type,
                resource_mode=resource_mode,
                confidence=round(rec.confidence, 3),
            )
        )

    return RecommendationResponse(recommendations=payload)


@router.post('/skills/{skill_id}/resources/generate', response_model=ResourceResponse)
async def generate_resource(
    skill_id: int,
    payload: GenerateResourceRequest,
    current_user: CurrentUser,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ResourceResponse:
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)

    try:
        resource, structured_content, source = await resource_agent.generate_material(
            db,
            user_id=current_user.id,
            topic=topic,
            skill_node=skill,
            kind=payload.kind,
            regenerate=regenerate,
        )
        profile_agent.record_generated_content(db, current_user.id, skill, payload.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return ResourceResponse(
        id=resource.id,
        skill_node_id=resource.skill_node_id,
        resource_type=resource.resource_type,
        title=resource.title,
        url=resource.url,
        summary=resource.summary,
        content=resource.content,
        structured_content=structured_content,
        source=source,
        version=resource.version,
        relevance_reason=resource.relevance_reason,
    )


@router.get('/skills/{skill_id}/resources/external', response_model=ExternalResourceResponse)
async def external_resources(
    skill_id: int,
    current_user: CurrentUser,
    limit: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
) -> ExternalResourceResponse:
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)

    try:
        resources = await resource_agent.fetch_external_resources(db, topic=topic, skill_node=skill, limit=limit)
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return ExternalResourceResponse(
        resources=[
            ExternalResourceItem(
                id=item.id,
                title=item.title,
                url=item.url,
                summary=item.summary,
                resource_type=item.resource_type,
                relevance_reason=item.relevance_reason,
            )
            for item in resources
        ]
    )


@router.get('/skills/{skill_id}/exercises/completions', response_model=ExerciseCompletionListResponse)
def list_exercise_completions(
    skill_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ExerciseCompletionListResponse:
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Skill node not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)
    return _exercise_completion_snapshot(db, user_id=current_user.id, skill=skill)


@router.post('/skills/{skill_id}/exercises/{exercise_index}/complete', response_model=ExerciseCompletionListResponse)
async def complete_exercise(
    skill_id: int,
    exercise_index: int,
    current_user: CurrentUser,
    proof: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> ExerciseCompletionListResponse:
    if exercise_index < 0:
        raise HTTPException(status_code=400, detail='exercise_index must be 0 or greater.')

    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Skill node not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)

    resource, exercise_items = _exercise_items_for_skill(
        db,
        user_id=current_user.id,
        skill_id=skill.id,
    )
    if resource is None or not exercise_items:
        raise HTTPException(
            status_code=409,
            detail='Generate exercises for this node first.',
        )
    if exercise_index >= len(exercise_items):
        raise HTTPException(
            status_code=400,
            detail=f'Exercise index {exercise_index} is out of range for this node.',
        )

    unlocked_before = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
    now = datetime.utcnow()
    title = str(exercise_items[exercise_index].get('title') or f'Exercise {exercise_index + 1}')[:180]
    completion = db.scalar(
        select(ExerciseCompletion).where(
            ExerciseCompletion.user_id == current_user.id,
            ExerciseCompletion.skill_node_id == skill.id,
            ExerciseCompletion.exercise_index == exercise_index,
        )
    )
    if completion is None:
        completion = ExerciseCompletion(
            user_id=current_user.id,
            topic_id=topic.id,
            skill_node_id=skill.id,
            resource_id=resource.id,
            exercise_index=exercise_index,
            exercise_title=title,
            completed_at=now,
        )
        db.add(completion)
        db.flush()
    else:
        completion.resource_id = resource.id
        completion.exercise_title = title
        completion.completed_at = now

    if proof is not None:
        content_type = (proof.content_type or '').strip().lower()
        if not (content_type.startswith('image/') or content_type == 'application/pdf'):
            raise HTTPException(status_code=400, detail='Only image or PDF proof uploads are supported.')
        data = await proof.read()
        if not data:
            raise HTTPException(status_code=400, detail='Uploaded proof file is empty.')
        max_bytes = max(1, int(settings.exercise_proof_max_mb)) * 1024 * 1024
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f'Proof upload is limited to {int(settings.exercise_proof_max_mb)}MB.',
            )

        suffix = Path(proof.filename or '').suffix.lower()
        if not suffix:
            suffix = '.pdf' if content_type == 'application/pdf' else '.png'

        base_dir = _exercise_proof_base_dir() / f'user-{current_user.id}' / f'topic-{topic.id}' / f'skill-{skill.id}'
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / f'exercise-{exercise_index + 1}-{uuid4().hex}{suffix}'
        file_path.write_bytes(data)

        if completion.proof_storage_path and completion.proof_storage_path != str(file_path):
            old_path = Path(completion.proof_storage_path)
            if old_path.exists():
                old_path.unlink(missing_ok=True)

        completion.proof_filename = proof.filename or file_path.name
        completion.proof_content_type = content_type or 'application/octet-stream'
        completion.proof_storage_path = str(file_path)
        completion.proof_size_bytes = len(data)

    db.commit()
    db.refresh(completion)

    state = _get_or_create_state_for_skill(db, user_id=current_user.id, skill=skill)
    if state.exercises_completed_at is None:
        profile_agent.apply_progress_event(
            db,
            user_id=current_user.id,
            skill_node=skill,
            action='complete_exercises',
        )
    else:
        state.last_activity_at = now
        db.commit()

    _invalidate_recommendations(db, topic.id, current_user.id)
    unlocked_after = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
    newly_unlocked_ids = sorted(unlocked_after - unlocked_before)
    if newly_unlocked_ids:
        topic_bootstrap_service.prepare_unlocked_nodes(
            topic_id=topic.id,
            user_id=current_user.id,
            node_ids=newly_unlocked_ids,
        )
    _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)
    return _exercise_completion_snapshot(db, user_id=current_user.id, skill=skill)


@router.get('/exercise-completions/{completion_id}/proof')
def get_exercise_completion_proof(
    completion_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> FileResponse:
    completion = db.scalar(
        select(ExerciseCompletion).where(
            ExerciseCompletion.id == completion_id,
            ExerciseCompletion.user_id == current_user.id,
        )
    )
    if completion is None:
        raise HTTPException(status_code=404, detail='Exercise completion not found')
    if not completion.proof_storage_path:
        raise HTTPException(status_code=404, detail='No proof file exists for this completion.')

    proof_path = Path(completion.proof_storage_path)
    if not proof_path.exists():
        raise HTTPException(status_code=404, detail='Proof file is missing from storage.')
    return FileResponse(
        path=proof_path,
        media_type=completion.proof_content_type or 'application/octet-stream',
        filename=completion.proof_filename or proof_path.name,
    )


@router.post('/assessments/generate', response_model=AssessmentDetailResponse)
async def generate_assessment(
    payload: AssessmentGenerateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssessmentDetailResponse:
    topic = _get_topic_or_404(db, payload.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    skill = _get_skill_or_404(db, payload.skill_node_id)
    if skill.topic_id != topic.id:
        raise HTTPException(status_code=400, detail='skill_node_id does not belong to this topic')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)
    try:
        await _ensure_assessment_source_material(
            db,
            user_id=current_user.id,
            topic=topic,
            skill=skill,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    question_count = payload.question_count
    if question_count is None:
        question_count = assessment_question_count_for_depth(normalize_course_depth(topic.course_depth))

    try:
        assessment, source = await assessment_agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill,
            user_id=current_user.id,
            question_count=question_count,
            regenerate=payload.regenerate,
            preferred_styles=payload.assessment_styles or None,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return _assessment_to_response(db, assessment=assessment, source=source)


@router.get('/assessments/{assessment_id}', response_model=AssessmentDetailResponse)
def get_assessment_detail(
    assessment_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssessmentDetailResponse:
    assessment = assessment_agent.get_assessment(db, assessment_id=assessment_id, user_id=current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail='Assessment not found')
    return _assessment_to_response(db, assessment=assessment, source='stored')


@router.post('/skills/{skill_id}/quiz/generate', response_model=QuizResponse)
async def generate_quiz_compat(
    skill_id: int,
    payload: QuizGenerateRequest,
    current_user: CurrentUser,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> QuizResponse:
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)
    try:
        await _ensure_assessment_source_material(
            db,
            user_id=current_user.id,
            topic=topic,
            skill=skill,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    try:
        assessment, source = await assessment_agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill,
            user_id=current_user.id,
            question_count=payload.num_questions,
            regenerate=regenerate,
            preferred_styles=None,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    questions = db.scalars(
        select(AssessmentQuestion)
        .where(
            AssessmentQuestion.assessment_id == assessment.id,
            AssessmentQuestion.question_type == AssessmentQuestionType.multiple_choice,
        )
        .order_by(AssessmentQuestion.order_index.asc())
    ).all()
    if not questions:
        raise HTTPException(
            status_code=400,
            detail='Assessment was generated without multiple-choice questions. Use /assessments/* endpoints.',
        )

    return QuizResponse(
        assessment_id=assessment.id,
        title=assessment.title,
        questions=[
            {
                'id': f'q{question.id}',
                'prompt': question.prompt,
                'choices': question.choices or [],
            }
            for question in questions
        ],
        source=source,
        version=assessment.version,
    )


@router.post('/assessments/{assessment_id}/submit', response_model=AssessmentSubmitResponse)
async def submit_assessment(
    assessment_id: int,
    payload: AssessmentSubmitRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssessmentSubmitResponse:
    assessment = assessment_agent.get_assessment(db, assessment_id=assessment_id, user_id=current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail='Assessment not found')

    topic = _get_topic_or_404(db, assessment.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Assessment not found')

    skill = _get_skill_or_404(db, assessment.skill_node_id)
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)
    unlocked_before = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
    mastery_eligible = not assessment.answers_revealed

    try:
        scored = await assessment_agent.score_assessment(
            db,
            assessment=assessment,
            topic=topic,
            skill_node=skill,
            user_id=current_user.id,
            responses=[item.model_dump() for item in payload.responses],
            mastery_eligible=mastery_eligible,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    if mastery_eligible:
        updated_state = profile_agent.apply_assessment_result(
            db,
            user_id=current_user.id,
            skill_node=skill,
            score=scored.overall_score,
            mastery_delta=scored.mastery_delta,
            confidence_signal=scored.confidence_avg if scored.confidence_avg > 0 else None,
        )
        _invalidate_recommendations(db, skill.topic_id, current_user.id)

        tree = _build_skill_tree_response(db, topic, current_user.id)
        unlocked_skill_ids = [node.id for node in tree.nodes if node.status != SkillStatus.locked]
        newly_unlocked_ids = sorted(set(unlocked_skill_ids) - unlocked_before)
        if newly_unlocked_ids:
            topic_bootstrap_service.prepare_unlocked_nodes(
                topic_id=topic.id,
                user_id=current_user.id,
                node_ids=newly_unlocked_ids,
            )
        _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)
        skill_graph_agent.create_performance_branch_suggestion(
            db,
            topic=topic,
            parent_node=skill,
            user_id=current_user.id,
            score=scored.overall_score,
        )
    else:
        profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
        updated_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == current_user.id,
                UserSkillState.skill_node_id == skill.id,
            )
        )
        if not updated_state:
            raise HTTPException(status_code=500, detail='Unable to load user skill state.')
        tree = _build_skill_tree_response(db, topic, current_user.id)
        unlocked_skill_ids = [node.id for node in tree.nodes if node.status != SkillStatus.locked]

    return AssessmentSubmitResponse(
        assessment_id=assessment.id,
        attempt_id=scored.attempt.id,
        score=round(scored.overall_score, 3),
        confidence_avg=round(scored.confidence_avg, 3),
        mastery_delta=round(scored.mastery_delta, 3),
        mastery_eligible=mastery_eligible,
        mastery_applied=mastery_eligible,
        practice_mode=not mastery_eligible,
        outcome_message=(
            'Practice attempt recorded. Mastery is unchanged because answers were revealed for this assessment.'
            if not mastery_eligible
            else 'Assessment submitted. Progress updated from your result.'
        ),
        feedback=[
            AssessmentQuestionFeedbackResponse(
                question_id=int(item['question_id']),
                question_type=AssessmentQuestionType(item['question_type']),
                assessment_style=str(item.get('assessment_style') or ''),
                score=float(item['score']) if item.get('score') is not None else None,
                confidence_score=item.get('confidence_score'),
                feedback=item['feedback'],
                missing_concepts=item.get('missing_concepts', []),
            )
            for item in scored.feedback
        ],
        strengths=scored.strengths,
        weaknesses=scored.weaknesses,
        review_next=scored.review_next,
        recommended_follow_up=scored.recommended_follow_up,
        summary=scored.summary,
        updated_mastery=round(updated_state.mastery, 3),
        updated_status=updated_state.status,
        updated_progress_state=updated_state.progress_state,  # type: ignore[arg-type]
        unlocked_skill_ids=unlocked_skill_ids,
    )


@router.post('/assessments/{assessment_id}/reveal-answers', response_model=AssessmentRevealResponse)
def reveal_assessment_answers(
    assessment_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssessmentRevealResponse:
    assessment = assessment_agent.get_assessment(db, assessment_id=assessment_id, user_id=current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail='Assessment not found')

    try:
        reveals = assessment_agent.reveal_answers(
            db,
            assessment=assessment,
            user_id=current_user.id,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return AssessmentRevealResponse(
        assessment_id=assessment.id,
        answers_revealed=True,
        mastery_eligible=False,
        warning=(
            'Answers are now revealed. This assessment is practice-only and will not count toward mastery. '
            'Generate a new assessment for a mastery-eligible attempt.'
        ),
        question_reveals=[
            AssessmentRevealQuestionResponse(
                question_id=int(item['question_id']),
                question_type=AssessmentQuestionType(item['question_type']),
                assessment_style=str(item.get('assessment_style') or ''),
                answer=str(item.get('answer') or ''),
                key_points=[str(point) for point in item.get('key_points', [])],
            )
            for item in reveals
        ],
    )


@router.get('/assessment-attempts/{attempt_id}', response_model=AssessmentAttemptResponse)
def get_assessment_attempt(
    attempt_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssessmentAttemptResponse:
    attempt = assessment_agent.get_attempt(db, attempt_id=attempt_id, user_id=current_user.id)
    if not attempt:
        raise HTTPException(status_code=404, detail='Assessment attempt not found')
    return _attempt_to_response(db, attempt=attempt)


@router.post('/assessments/{assessment_id}/submit-quiz', response_model=QuizSubmitResponse)
async def submit_quiz_compat(
    assessment_id: int,
    payload: QuizSubmitRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> QuizSubmitResponse:
    assessment = assessment_agent.get_assessment(db, assessment_id=assessment_id, user_id=current_user.id)
    if not assessment:
        raise HTTPException(status_code=404, detail='Assessment not found')

    questions = db.scalars(
        select(AssessmentQuestion)
        .where(AssessmentQuestion.assessment_id == assessment.id)
        .order_by(AssessmentQuestion.order_index.asc())
    ).all()
    if not questions:
        raise HTTPException(status_code=400, detail='Assessment has no questions')

    responses = []
    for idx, question in enumerate(questions):
        if question.question_type != AssessmentQuestionType.multiple_choice:
            responses.append(
                {
                    'question_id': question.id,
                    'answer_text': '',
                }
            )
            continue
        selected = payload.answers[idx] if idx < len(payload.answers) else -1
        responses.append(
            {
                'question_id': question.id,
                'selected_option_index': selected,
                'answer_text': '',
            }
        )

    topic = _get_topic_or_404(db, assessment.topic_id)
    skill = _get_skill_or_404(db, assessment.skill_node_id)
    unlocked_before = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
    mastery_eligible = not assessment.answers_revealed
    scored = await assessment_agent.score_assessment(
        db,
        assessment=assessment,
        topic=topic,
        skill_node=skill,
        user_id=current_user.id,
        responses=responses,
        mastery_eligible=mastery_eligible,
    )
    if mastery_eligible:
        updated_state = profile_agent.apply_assessment_result(
            db,
            user_id=current_user.id,
            skill_node=skill,
            score=scored.overall_score,
            mastery_delta=scored.mastery_delta,
            confidence_signal=scored.confidence_avg if scored.confidence_avg > 0 else None,
        )
        _invalidate_recommendations(db, skill.topic_id, current_user.id)
        unlocked_after = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
        newly_unlocked_ids = sorted(unlocked_after - unlocked_before)
        if newly_unlocked_ids:
            topic_bootstrap_service.prepare_unlocked_nodes(
                topic_id=topic.id,
                user_id=current_user.id,
                node_ids=newly_unlocked_ids,
            )
        _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)
        skill_graph_agent.create_performance_branch_suggestion(
            db,
            topic=topic,
            parent_node=skill,
            user_id=current_user.id,
            score=scored.overall_score,
        )
    else:
        profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
        updated_state = db.scalar(
            select(UserSkillState).where(
                UserSkillState.user_id == current_user.id,
                UserSkillState.skill_node_id == skill.id,
            )
        )
        if not updated_state:
            raise HTTPException(status_code=500, detail='Unable to load user skill state.')

    return QuizSubmitResponse(
        score=round(scored.overall_score, 3),
        feedback=scored.feedback,
        updated_mastery=round(updated_state.mastery, 3),
        updated_status=updated_state.status,
        updated_progress_state=updated_state.progress_state,  # type: ignore[arg-type]
    )


@router.post('/skills/{skill_id}/progress/update', response_model=MasteryUpdateResponse)
async def update_progress(
    skill_id: int,
    payload: MasteryUpdateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> MasteryUpdateResponse:
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Skill node not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=skill)
    unlocked_before = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)

    try:
        state = profile_agent.apply_progress_event(
            db,
            user_id=current_user.id,
            skill_node=skill,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_recommendations(db, skill.topic_id, current_user.id)
    unlocked_after = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
    newly_unlocked_ids = sorted(unlocked_after - unlocked_before)
    if newly_unlocked_ids:
        topic_bootstrap_service.prepare_unlocked_nodes(
            topic_id=topic.id,
            user_id=current_user.id,
            node_ids=newly_unlocked_ids,
        )
    _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)

    return MasteryUpdateResponse(
        skill_node_id=skill_id,
        mastery=round(state.mastery, 3),
        status=state.status,
        progress_state=state.progress_state,  # type: ignore[arg-type]
    )


@router.post('/skills/{skill_id}/force-unlock', response_model=MasteryUpdateResponse)
async def force_unlock_skill(
    skill_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> MasteryUpdateResponse:
    if not _current_user_can_force_unlock(current_user):
        raise HTTPException(status_code=403, detail='Dev unlock is not enabled for this account.')

    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Skill node not found')

    state = _get_or_create_state_for_skill(db, user_id=current_user.id, skill=skill)
    state.force_unlocked = True
    if state.progress_state == 'verified':
        state.status = SkillStatus.mastered
    elif state.progress_state in ('learning', 'completed'):
        state.status = SkillStatus.in_progress
    else:
        state.status = SkillStatus.available
    state.last_activity_at = datetime.utcnow()
    db.commit()
    db.refresh(state)

    _invalidate_recommendations(db, topic.id, current_user.id)
    topic_bootstrap_service.prepare_unlocked_nodes(
        topic_id=topic.id,
        user_id=current_user.id,
        node_ids=[skill.id],
    )
    _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)

    return MasteryUpdateResponse(
        skill_node_id=skill_id,
        mastery=round(state.mastery, 3),
        status=state.status,
        progress_state=state.progress_state,  # type: ignore[arg-type]
    )


@router.get('/topics/{topic_id}/progress', response_model=TopicProgressResponse)
def get_topic_progress(
    topic_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TopicProgressResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    profile_agent.ensure_states_for_topic(db, current_user.id, topic_id)
    profile_agent.recompute_unlocks(db, current_user.id, topic_id)
    tree = _build_skill_tree_response(db, topic, current_user.id)

    total_nodes = len(tree.nodes)
    verified_nodes = sum(1 for node in tree.nodes if node.progress_state == 'verified')
    available_nodes = sum(1 for node in tree.nodes if node.status != SkillStatus.locked)
    mastery_average = round(mean(node.mastery_estimate for node in tree.nodes), 3) if tree.nodes else 0.0
    tree_stage = _topic_tree_stage(
        total_nodes=total_nodes,
        verified_nodes=verified_nodes,
        available_nodes=available_nodes,
        mastery_average=mastery_average,
    )

    return TopicProgressResponse(
        topic_id=topic.id,
        topic_name=topic.name,
        total_nodes=total_nodes,
        verified_nodes=verified_nodes,
        available_nodes=available_nodes,
        mastery_average=mastery_average,
        tree_stage=tree_stage,
        nodes=[
            TopicProgressNode(
                skill_node_id=node.id,
                name=node.name,
                status=node.status,
                progress_state=node.progress_state,  # type: ignore[arg-type]
                mastery=node.mastery_estimate,
                best_quiz_score=node.best_quiz_score or 0.0,
                recommended_next_action=node.recommended_next_action,
            )
            for node in tree.nodes
        ],
    )


@router.get('/topics/{topic_id}/retention-loop', response_model=TopicRetentionLoopResponse)
def get_topic_retention_loop(
    topic_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> TopicRetentionLoopResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    profile_agent.ensure_states_for_topic(db, current_user.id, topic_id)
    profile_agent.recompute_unlocks(db, current_user.id, topic_id)
    tree = _build_skill_tree_response(db, topic, current_user.id)

    total_nodes = len(tree.nodes)
    verified_nodes = sum(1 for node in tree.nodes if node.progress_state == 'verified')
    available_nodes = sum(1 for node in tree.nodes if node.status != SkillStatus.locked)
    mastery_average = round(mean(node.mastery_estimate for node in tree.nodes), 3) if tree.nodes else 0.0
    tree_stage = _topic_tree_stage(
        total_nodes=total_nodes,
        verified_nodes=verified_nodes,
        available_nodes=available_nodes,
        mastery_average=mastery_average,
    )

    loop = retention_service.build_topic_loop(
        db,
        topic=topic,
        user_id=current_user.id,
        tree_stage=tree_stage,
    )
    cadence = loop['cadence']
    plan_summary = (
        'Today: focus on your top immediate actions and keep momentum.'
        if cadence == 'daily'
        else 'This week: complete key actions and target your next unlock.'
    )

    return TopicRetentionLoopResponse(
        topic_id=topic.id,
        topic_name=topic.name,
        cadence=cadence,  # type: ignore[arg-type]
        plan_summary=plan_summary,
        next_actions=[_action_to_response(item) for item in loop['next_actions']],
        learning_plan=[_action_to_response(item) for item in loop['plan_items']],
        unlock_anticipation=_unlock_to_response(loop['unlock_anticipation']),
        reminder=_reminder_to_response(loop['reminder']),
        milestones=[_milestone_to_response(item) for item in loop['milestones']],
        total_nodes=total_nodes,
        available_nodes=loop['available_nodes'],
        verified_nodes=loop['verified_nodes'],
        completed_nodes=loop['completed_nodes'],
        lessons_completed=loop['lessons_completed'],
        assessments_taken=loop['assessments_taken'],
        mastery_average=loop['mastery_average'],
        tree_stage=tree_stage,
        streak_days=loop['streak_days'],
        activity_days_last_14=loop['activity_days_last_14'],
        latest_activity_at=loop['latest_activity_at'],
        dev_unlock_enabled=_current_user_can_force_unlock(current_user),
    )


@router.post('/topics/{topic_id}/milestones/{milestone_id}/seen', response_model=MilestoneEventResponse)
def mark_milestone_seen(
    topic_id: int,
    milestone_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> MilestoneEventResponse:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    event = retention_service.mark_milestone_seen(
        db,
        milestone_id=milestone_id,
        topic_id=topic_id,
        user_id=current_user.id,
    )
    if not event:
        raise HTTPException(status_code=404, detail='Milestone not found')
    return _milestone_to_response(event)


@router.post('/topics/{topic_id}/reminders/{reminder_id}/dismiss', status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def dismiss_topic_reminder(
    topic_id: int,
    reminder_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    reminder = retention_service.dismiss_reminder(
        db,
        reminder_id=reminder_id,
        topic_id=topic_id,
        user_id=current_user.id,
    )
    if reminder is None:
        raise HTTPException(status_code=404, detail='Reminder not found')
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/users/me/progress-summary', response_model=UserProgressSummaryResponse)
def get_user_progress_summary(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> UserProgressSummaryResponse:
    topics = db.scalars(
        select(Topic).where(Topic.user_id == current_user.id).order_by(Topic.created_at.desc())
    ).all()

    topic_summaries: list[UserTopicProgressSummary] = []
    verified_total = 0
    mastery_values: list[float] = []

    for topic in topics:
        profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
        profile_agent.recompute_unlocks(db, current_user.id, topic.id)
        tree = _build_skill_tree_response(db, topic, current_user.id)
        verified_nodes = sum(1 for node in tree.nodes if node.progress_state == 'verified')
        available_nodes = sum(1 for node in tree.nodes if node.status != SkillStatus.locked)
        avg_mastery = round(mean(node.mastery_estimate for node in tree.nodes), 3) if tree.nodes else 0.0
        tree_stage = _topic_tree_stage(
            total_nodes=len(tree.nodes),
            verified_nodes=verified_nodes,
            available_nodes=available_nodes,
            mastery_average=avg_mastery,
        )
        verified_total += verified_nodes
        mastery_values.append(avg_mastery)
        topic_summaries.append(
            UserTopicProgressSummary(
                topic_id=topic.id,
                topic_name=topic.name,
                total_nodes=len(tree.nodes),
                verified_nodes=verified_nodes,
                mastery_average=avg_mastery,
                tree_stage=tree_stage,
            )
        )

    return UserProgressSummaryResponse(
        user_id=current_user.id,
        xp=current_user.xp,
        level=current_user.level,
        topics_total=len(topics),
        verified_nodes_total=verified_total,
        mastery_average=round(mean(mastery_values), 3) if mastery_values else 0.0,
        topics=topic_summaries,
    )


@router.post('/skills/{skill_id}/deep-dive', response_model=SkillTreeResponse)
async def create_deep_dive_branch(
    skill_id: int,
    payload: DeepDiveBranchRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SkillTreeResponse:
    parent_skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, parent_skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=parent_skill)
    unlocked_before = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)

    try:
        await skill_graph_agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent_skill,
            user_id=current_user.id,
            focus=payload.focus.strip() or None,
            branch_size=payload.branch_size,
            branch_origin='user_requested',
            branch_purpose=payload.purpose,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
    profile_agent.recompute_unlocks(db, current_user.id, topic.id)
    _invalidate_recommendations(db, topic.id, current_user.id)
    unlocked_after = _collect_unlocked_skill_ids(db, topic_id=topic.id, user_id=current_user.id)
    newly_unlocked_ids = sorted(unlocked_after - unlocked_before)
    if newly_unlocked_ids:
        topic_bootstrap_service.prepare_unlocked_nodes(
            topic_id=topic.id,
            user_id=current_user.id,
            node_ids=newly_unlocked_ids,
        )
    _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)
    return _build_skill_tree_response(db, topic, current_user.id)


@router.get('/skills/{skill_id}/branch-suggestions', response_model=BranchSuggestionListResponse)
def list_branch_suggestions(
    skill_id: int,
    current_user: CurrentUser,
    status_filter: Literal['pending', 'accepted', 'rejected', 'all'] = Query(default='pending'),
    db: Session = Depends(get_db),
) -> BranchSuggestionListResponse:
    parent_skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, parent_skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')

    stmt = select(BranchSuggestion).where(
        BranchSuggestion.topic_id == topic.id,
        BranchSuggestion.user_id == current_user.id,
        BranchSuggestion.parent_skill_id == parent_skill.id,
    )
    if status_filter != 'all':
        stmt = stmt.where(BranchSuggestion.status == status_filter)
    suggestions = db.scalars(stmt.order_by(BranchSuggestion.created_at.desc())).all()
    return BranchSuggestionListResponse(
        suggestions=[_branch_suggestion_to_response(item) for item in suggestions]
    )


@router.post('/skills/{skill_id}/branch-suggestions/generate', response_model=BranchSuggestionListResponse)
async def generate_branch_suggestions(
    skill_id: int,
    payload: BranchSuggestionGenerateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BranchSuggestionListResponse:
    parent_skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, parent_skill.topic_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=parent_skill)

    try:
        await skill_graph_agent.suggest_branch_paths(
            db,
            topic=topic,
            parent_node=parent_skill,
            user_id=current_user.id,
            limit=payload.limit,
            trigger_event=payload.trigger_event,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    suggestions = db.scalars(
        select(BranchSuggestion)
        .where(
            BranchSuggestion.topic_id == topic.id,
            BranchSuggestion.user_id == current_user.id,
            BranchSuggestion.parent_skill_id == parent_skill.id,
            BranchSuggestion.status == 'pending',
        )
        .order_by(BranchSuggestion.created_at.desc())
    ).all()
    return BranchSuggestionListResponse(
        suggestions=[_branch_suggestion_to_response(item) for item in suggestions]
    )


@router.post('/branch-suggestions/{suggestion_id}/accept', response_model=SkillTreeResponse)
async def accept_branch_suggestion(
    suggestion_id: int,
    current_user: CurrentUser,
    branch_size: int = Query(default=3, ge=2, le=5),
    db: Session = Depends(get_db),
) -> SkillTreeResponse:
    suggestion = db.scalar(
        select(BranchSuggestion).where(
            BranchSuggestion.id == suggestion_id,
            BranchSuggestion.user_id == current_user.id,
        )
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail='Branch suggestion not found')
    if suggestion.status == 'rejected':
        raise HTTPException(status_code=400, detail='Branch suggestion was rejected and cannot be accepted.')

    topic = _get_topic_or_404(db, suggestion.topic_id)
    parent_skill = _get_skill_or_404(db, suggestion.parent_skill_id)
    if topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Topic not found')
    _assert_skill_unlocked_for_learning(db, user_id=current_user.id, skill=parent_skill)

    created_nodes: list[SkillNode] = []
    if suggestion.status != 'accepted':
        try:
            created_nodes = await skill_graph_agent.create_deep_dive_branch(
                db,
                topic=topic,
                parent_node=parent_skill,
                user_id=current_user.id,
                focus=suggestion.focus,
                branch_size=branch_size,
                branch_origin='system_suggested',
                branch_purpose=suggestion.purpose,
            )
        except Exception as exc:  # noqa: BLE001
            _raise_service_error(exc)

        suggestion.status = 'accepted'
        suggestion.accepted_branch_root_skill_id = created_nodes[0].id if created_nodes else None
        suggestion.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(suggestion)

    profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
    profile_agent.recompute_unlocks(db, current_user.id, topic.id)
    _invalidate_recommendations(db, topic.id, current_user.id)
    _ensure_topic_milestone_events(db, topic=topic, user_id=current_user.id)
    return _build_skill_tree_response(db, topic, current_user.id)


@router.post('/branch-suggestions/{suggestion_id}/reject', response_model=BranchSuggestionResponse)
def reject_branch_suggestion(
    suggestion_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BranchSuggestionResponse:
    suggestion = db.scalar(
        select(BranchSuggestion).where(
            BranchSuggestion.id == suggestion_id,
            BranchSuggestion.user_id == current_user.id,
        )
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail='Branch suggestion not found')
    if suggestion.status != 'accepted':
        suggestion.status = 'rejected'
        suggestion.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(suggestion)
    return _branch_suggestion_to_response(suggestion)
