from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from statistics import mean

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
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
from app.core.exceptions import ConfigurationError, ProviderError
from app.db.database import get_db
from app.db.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    AssessmentQuestionType,
    AssessmentResponse,
    Document,
    DocumentChunk,
    LearningResource,
    Note,
    Recommendation,
    ChatMessage,
    ChatSession,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    TopicInitializationJob,
    UserSkillState,
)
from app.schemas.api import (
    AssessmentAttemptResponse,
    AssessmentDetailResponse,
    AssessmentGenerateRequest,
    AssessmentQuestionFeedbackResponse,
    AssessmentQuestionResponse,
    AssessmentSubmitRequest,
    AssessmentSubmitResponse,
    ChatRequest,
    ChatResponse,
    AppendTutorResponseToNoteRequest,
    SaveTutorResponseToNoteRequest,
    TutorNoteSaveResponse,
    DeepDiveBranchRequest,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentUploadResponse,
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
    TopicCreateRequest,
    TopicInitializationResponse,
    TopicInitializationStatusResponse,
    TopicListResponse,
    TopicProgressNode,
    TopicProgressResponse,
    TopicResponse,
    UserProgressSummaryResponse,
    UserTopicProgressSummary,
)
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService
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
topic_bootstrap_service = TopicBootstrapService(
    skill_graph_agent=skill_graph_agent,
    profile_agent=profile_agent,
    recommendation_agent=recommendation_agent,
    resource_agent=resource_agent,
    assessment_agent=assessment_agent,
)


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
                branch_parent_skill_id=node.branch_parent_skill_id,
                mastery_estimate=round(float(mastery), 3),
                status=node_status,
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
            score=round(row.score, 3),
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
    assessment_ids = db.scalars(select(Assessment.id).where(Assessment.topic_id == topic_id)).all()

    if assessment_ids:
        db.execute(delete(AssessmentAttempt).where(AssessmentAttempt.assessment_id.in_(assessment_ids)))

    db.execute(delete(ChatMessage).where(ChatMessage.topic_id == topic_id))
    db.execute(delete(ChatSession).where(ChatSession.topic_id == topic_id))
    db.execute(
        delete(Recommendation).where(Recommendation.topic_id == topic_id, Recommendation.user_id == current_user.id)
    )
    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id.in_(select(Document.id).where(Document.topic_id == topic_id, Document.user_id == current_user.id))
        )
    )
    db.execute(delete(Document).where(Document.topic_id == topic_id, Document.user_id == current_user.id))
    db.execute(delete(Note).where(Note.topic_id == topic_id, Note.user_id == current_user.id))
    db.execute(delete(LearningResource).where(LearningResource.topic_id == topic_id))
    db.execute(delete(Assessment).where(Assessment.topic_id == topic_id, Assessment.user_id == current_user.id))
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
        assessment, source = await assessment_agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill,
            user_id=current_user.id,
            question_count=payload.question_count,
            regenerate=payload.regenerate,
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
        assessment, source = await assessment_agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill,
            user_id=current_user.id,
            question_count=payload.num_questions,
            regenerate=regenerate,
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

    try:
        scored = await assessment_agent.score_assessment(
            db,
            assessment=assessment,
            topic=topic,
            skill_node=skill,
            user_id=current_user.id,
            responses=[item.model_dump() for item in payload.responses],
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

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

    return AssessmentSubmitResponse(
        assessment_id=assessment.id,
        attempt_id=scored.attempt.id,
        score=round(scored.overall_score, 3),
        confidence_avg=round(scored.confidence_avg, 3),
        mastery_delta=round(scored.mastery_delta, 3),
        feedback=[
            AssessmentQuestionFeedbackResponse(
                question_id=int(item['question_id']),
                question_type=AssessmentQuestionType(item['question_type']),
                score=float(item['score']),
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
                    'confidence_score': 0.5,
                }
            )
            continue
        selected = payload.answers[idx] if idx < len(payload.answers) else -1
        responses.append(
            {
                'question_id': question.id,
                'selected_option_index': selected,
                'answer_text': '',
                'confidence_score': 0.7,
            }
        )

    topic = _get_topic_or_404(db, assessment.topic_id)
    skill = _get_skill_or_404(db, assessment.skill_node_id)
    scored = await assessment_agent.score_assessment(
        db,
        assessment=assessment,
        topic=topic,
        skill_node=skill,
        user_id=current_user.id,
        responses=responses,
    )
    updated_state = profile_agent.apply_assessment_result(
        db,
        user_id=current_user.id,
        skill_node=skill,
        score=scored.overall_score,
        mastery_delta=scored.mastery_delta,
        confidence_signal=scored.confidence_avg if scored.confidence_avg > 0 else None,
    )
    _invalidate_recommendations(db, skill.topic_id, current_user.id)

    return QuizSubmitResponse(
        score=round(scored.overall_score, 3),
        feedback=scored.feedback,
        updated_mastery=round(updated_state.mastery, 3),
        updated_status=updated_state.status,
        updated_progress_state=updated_state.progress_state,  # type: ignore[arg-type]
    )


@router.post('/skills/{skill_id}/progress/update', response_model=MasteryUpdateResponse)
def update_progress(
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

    return TopicProgressResponse(
        topic_id=topic.id,
        topic_name=topic.name,
        total_nodes=total_nodes,
        verified_nodes=verified_nodes,
        available_nodes=available_nodes,
        mastery_average=mastery_average,
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
        avg_mastery = round(mean(node.mastery_estimate for node in tree.nodes), 3) if tree.nodes else 0.0
        verified_total += verified_nodes
        mastery_values.append(avg_mastery)
        topic_summaries.append(
            UserTopicProgressSummary(
                topic_id=topic.id,
                topic_name=topic.name,
                total_nodes=len(tree.nodes),
                verified_nodes=verified_nodes,
                mastery_average=avg_mastery,
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

    try:
        await skill_graph_agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent_skill,
            user_id=current_user.id,
            focus=payload.focus.strip() or None,
            branch_size=payload.branch_size,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.ensure_states_for_topic(db, current_user.id, topic.id)
    profile_agent.recompute_unlocks(db, current_user.id, topic.id)
    _invalidate_recommendations(db, topic.id, current_user.id)
    return _build_skill_tree_response(db, topic, current_user.id)
