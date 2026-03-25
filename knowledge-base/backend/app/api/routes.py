from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher

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
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, ProviderError
from app.db.database import get_db
from app.db.models import (
    Assessment,
    AssessmentAttempt,
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
    User,
    UserSkillState,
)
from app.schemas.api import (
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
    TopicListResponse,
    TopicResponse,
)
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.retrieval import RetrievalService
from app.services.search import ExternalSearchService
from app.utils.text import extract_text_from_upload


router = APIRouter()
settings = get_settings()

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


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, ConfigurationError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(exc, ProviderError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _get_or_create_user(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user:
        return user

    if user_id != 1:
        raise HTTPException(status_code=404, detail='User not found')

    user = User(id=1, email=settings.default_user_email, display_name='Demo User')
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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


@router.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/topics', response_model=TopicListResponse)
def list_topics(user_id: int = Query(default=1), db: Session = Depends(get_db)) -> TopicListResponse:
    _get_or_create_user(db, user_id)
    topics = db.scalars(select(Topic).where(Topic.user_id == user_id).order_by(Topic.created_at.desc())).all()
    return TopicListResponse(topics=[_topic_to_response(topic) for topic in topics])


@router.post('/topics', response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(payload: TopicCreateRequest, db: Session = Depends(get_db)) -> TopicResponse:
    _get_or_create_user(db, payload.user_id)

    topic = Topic(
        user_id=payload.user_id,
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

    profile_agent.ensure_states_for_topic(db, payload.user_id, topic.id)
    return _topic_to_response(topic)


@router.delete('/topics/{topic_id}', status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_topic(
    topic_id: int,
    user_id: int = Query(default=1),
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Response:
    _get_or_create_user(db, user_id)
    topic = _get_topic_or_404(db, topic_id)

    if topic.user_id != user_id:
        raise HTTPException(status_code=404, detail='Topic not found')
    if not confirm:
        raise HTTPException(status_code=400, detail='Set confirm=true to delete this topic.')

    skill_ids = db.scalars(select(SkillNode.id).where(SkillNode.topic_id == topic_id)).all()
    assessment_ids = db.scalars(select(Assessment.id).where(Assessment.topic_id == topic_id)).all()

    if assessment_ids:
        db.execute(delete(AssessmentAttempt).where(AssessmentAttempt.assessment_id.in_(assessment_ids)))

    db.execute(delete(ChatMessage).where(ChatMessage.topic_id == topic_id))
    db.execute(delete(ChatSession).where(ChatSession.topic_id == topic_id))
    db.execute(delete(Recommendation).where(Recommendation.topic_id == topic_id, Recommendation.user_id == user_id))
    db.execute(delete(DocumentChunk).where(DocumentChunk.topic_id == topic_id))
    db.execute(delete(Document).where(Document.topic_id == topic_id, Document.user_id == user_id))
    db.execute(delete(Note).where(Note.topic_id == topic_id, Note.user_id == user_id))
    db.execute(delete(LearningResource).where(LearningResource.topic_id == topic_id))
    db.execute(delete(Assessment).where(Assessment.topic_id == topic_id, Assessment.user_id == user_id))
    db.execute(delete(SkillEdge).where(SkillEdge.topic_id == topic_id))
    if skill_ids:
        db.execute(delete(UserSkillState).where(UserSkillState.user_id == user_id, UserSkillState.skill_node_id.in_(skill_ids)))
    db.execute(delete(SkillNode).where(SkillNode.topic_id == topic_id))
    db.delete(topic)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/topics/{topic_id}/skill-tree/generate', response_model=SkillTreeResponse)
async def generate_skill_tree(
    topic_id: int,
    user_id: int = Query(default=1),
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> SkillTreeResponse:
    _get_or_create_user(db, user_id)
    topic = _get_topic_or_404(db, topic_id)

    existing = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
    if existing and not regenerate:
        profile_agent.ensure_states_for_topic(db, user_id, topic.id)
        profile_agent.recompute_unlocks(db, user_id, topic.id)
        return _build_skill_tree_response(db, topic, user_id)

    if existing and regenerate:
        db.execute(delete(SkillEdge).where(SkillEdge.topic_id == topic.id))
        db.execute(delete(SkillNode).where(SkillNode.topic_id == topic.id))
        db.commit()

    try:
        await skill_graph_agent.create_skill_tree(db, topic)
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.ensure_states_for_topic(db, user_id, topic.id)
    profile_agent.recompute_unlocks(db, user_id, topic.id)
    return _build_skill_tree_response(db, topic, user_id)


@router.get('/topics/{topic_id}/skill-tree', response_model=SkillTreeResponse)
def get_skill_tree(topic_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> SkillTreeResponse:
    _get_or_create_user(db, user_id)
    topic = _get_topic_or_404(db, topic_id)
    profile_agent.ensure_states_for_topic(db, user_id, topic_id)
    profile_agent.recompute_unlocks(db, user_id, topic_id)
    return _build_skill_tree_response(db, topic, user_id)


@router.post('/topics/{topic_id}/documents/upload', response_model=DocumentUploadResponse)
@router.post('/topics/{topic_id}/notes/upload', response_model=DocumentUploadResponse)
async def upload_document(
    topic_id: int,
    user_id: int = Form(default=1),
    raw_text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)

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
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            text=text,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.infer_mastery_from_notes(db, user_id, topic_id)
    _invalidate_recommendations(db, topic_id, user_id)

    return DocumentUploadResponse(document_id=doc.id, filename=doc.filename, chunks_created=chunks)


@router.get('/topics/{topic_id}/documents', response_model=DocumentListResponse)
def list_documents(topic_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> DocumentListResponse:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)

    docs = db.scalars(
        select(Document)
        .where(Document.topic_id == topic_id, Document.user_id == user_id, Document.note_id.is_(None))
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
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
) -> Response:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)
    document = _get_document_or_404(db, topic_id, document_id, user_id)
    if document.note_id is not None:
        raise HTTPException(status_code=400, detail='This document is linked to a note and cannot be deleted here.')

    db.delete(document)
    db.commit()
    profile_agent.infer_mastery_from_notes(db, user_id, topic_id)
    _invalidate_recommendations(db, topic_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get('/topics/{topic_id}/notes', response_model=NoteListResponse)
def list_notes(
    topic_id: int,
    user_id: int = Query(default=1),
    skill_node_id: int | None = Query(default=None),
    query: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> NoteListResponse:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)

    stmt = select(Note).where(Note.topic_id == topic_id, Note.user_id == user_id)
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
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
) -> NoteResponse:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)

    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail='Note body cannot be empty')

    if payload.skill_node_id is not None:
        skill = _get_skill_or_404(db, payload.skill_node_id)
        if skill.topic_id != topic_id:
            raise HTTPException(status_code=400, detail='skill_node_id does not belong to this topic')

    title = payload.title.strip() or _generate_note_title(body)
    note = Note(
        user_id=user_id,
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
def get_note(note_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> NoteResponse:
    _get_or_create_user(db, user_id)
    note = _get_note_or_404(db, note_id, user_id)
    return _note_to_response(note)


@router.put('/notes/{note_id}', response_model=NoteResponse)
async def update_note(
    note_id: int,
    payload: NoteUpdateRequest,
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
) -> NoteResponse:
    _get_or_create_user(db, user_id)
    note = _get_note_or_404(db, note_id, user_id)

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
def delete_note(note_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> Response:
    _get_or_create_user(db, user_id)
    note = _get_note_or_404(db, note_id, user_id)
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(select(Document.id).where(Document.note_id == note.id))))
    db.execute(delete(Document).where(Document.note_id == note.id))
    db.delete(note)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/topics/{topic_id}/chat', response_model=ChatResponse)
async def chat(topic_id: int, payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    _get_or_create_user(db, payload.user_id)
    topic = _get_topic_or_404(db, topic_id)

    try:
        session_id, assistant_message_id, answer, used_chunks, structured_answer, context_usage, citations = await tutor_agent.respond(
            db,
            topic=topic,
            user_id=payload.user_id,
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
    db: Session = Depends(get_db),
) -> TutorNoteSaveResponse:
    _get_or_create_user(db, payload.user_id)
    topic = _get_topic_or_404(db, topic_id)
    if topic.user_id != payload.user_id:
        raise HTTPException(status_code=404, detail='Topic not found')

    session, message = _get_assistant_message_or_404(
        db,
        topic_id=topic_id,
        session_id=session_id,
        message_id=message_id,
        user_id=payload.user_id,
    )

    existing = db.scalar(
        select(Note).where(
            Note.user_id == payload.user_id,
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
        user_id=payload.user_id,
        topic_id=topic_id,
        body=resolved_body,
    )
    target_skill_id = payload.skill_node_id if payload.skill_node_id is not None else message.skill_node_id
    if target_skill_id is not None:
        skill = _get_skill_or_404(db, target_skill_id)
        if skill.topic_id != topic_id:
            raise HTTPException(status_code=400, detail='skill_node_id does not belong to this topic')

    note = Note(
        user_id=payload.user_id,
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
    profile_agent.infer_mastery_from_notes(db, payload.user_id, topic_id)
    _invalidate_recommendations(db, topic_id, payload.user_id)

    return TutorNoteSaveResponse(
        note=_note_to_response(note),
        duplicate_warning=duplicate_warning,
        appended=False,
    )


@router.post('/notes/{note_id}/append-tutor-response', response_model=TutorNoteSaveResponse)
async def append_tutor_response_to_existing_note(
    note_id: int,
    payload: AppendTutorResponseToNoteRequest,
    db: Session = Depends(get_db),
) -> TutorNoteSaveResponse:
    _get_or_create_user(db, payload.user_id)
    note = _get_note_or_404(db, note_id, payload.user_id)
    topic = _get_topic_or_404(db, note.topic_id)

    _session, message = _get_assistant_message_or_404(
        db,
        topic_id=note.topic_id,
        session_id=payload.session_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
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
        user_id=payload.user_id,
        topic_id=note.topic_id,
        body=append_clean,
    )

    db.commit()
    db.refresh(note)
    await _reindex_note_document(db, note=note)
    profile_agent.infer_mastery_from_notes(db, payload.user_id, note.topic_id)
    _invalidate_recommendations(db, note.topic_id, payload.user_id)

    return TutorNoteSaveResponse(
        note=_note_to_response(note),
        duplicate_warning=duplicate_warning,
        appended=True,
    )


@router.get('/topics/{topic_id}/recommendations', response_model=RecommendationResponse)
async def get_recommendations(
    topic_id: int,
    user_id: int = Query(default=1),
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    _get_or_create_user(db, user_id)
    topic = _get_topic_or_404(db, topic_id)

    profile_agent.ensure_states_for_topic(db, user_id, topic_id)
    profile_agent.recompute_unlocks(db, user_id, topic_id)

    records: list[Recommendation]
    if not refresh:
        freshness_cutoff = datetime.utcnow() - timedelta(minutes=3)
        cached = db.scalars(
            select(Recommendation)
            .where(Recommendation.topic_id == topic_id, Recommendation.user_id == user_id)
            .order_by(Recommendation.created_at.desc())
        ).all()
        if cached and cached[0].created_at >= freshness_cutoff:
            records = cached
        else:
            try:
                records = await recommendation_agent.generate_recommendations(db, topic, user_id)
            except Exception as exc:  # noqa: BLE001
                _raise_service_error(exc)
    else:
        try:
            records = await recommendation_agent.generate_recommendations(db, topic, user_id)
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
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ResourceResponse:
    _get_or_create_user(db, payload.user_id)
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    _assert_skill_unlocked_for_learning(db, user_id=payload.user_id, skill=skill)

    try:
        resource, structured_content, source = await resource_agent.generate_material(
            db,
            user_id=payload.user_id,
            topic=topic,
            skill_node=skill,
            kind=payload.kind,
            regenerate=regenerate,
        )
        profile_agent.record_generated_content(db, payload.user_id, skill, payload.kind)
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
    user_id: int = Query(default=1),
    limit: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
) -> ExternalResourceResponse:
    _get_or_create_user(db, user_id)
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    _assert_skill_unlocked_for_learning(db, user_id=user_id, skill=skill)

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


@router.post('/skills/{skill_id}/quiz/generate', response_model=QuizResponse)
async def generate_quiz(
    skill_id: int,
    payload: QuizGenerateRequest,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> QuizResponse:
    _get_or_create_user(db, payload.user_id)
    skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, skill.topic_id)
    _assert_skill_unlocked_for_learning(db, user_id=payload.user_id, skill=skill)

    try:
        assessment, source = await assessment_agent.generate_quiz(
            db,
            topic=topic,
            skill_node=skill,
            user_id=payload.user_id,
            num_questions=payload.num_questions,
            regenerate=regenerate,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return QuizResponse(
        assessment_id=assessment.id,
        title=assessment.title,
        questions=[
            {
                'id': question.get('id', f'q{idx+1}'),
                'prompt': question.get('prompt', ''),
                'choices': question.get('choices', []),
            }
            for idx, question in enumerate(assessment.questions)
        ],
        source=source,
        version=assessment.version,
    )


@router.post('/assessments/{assessment_id}/submit', response_model=QuizSubmitResponse)
def submit_quiz(assessment_id: int, payload: QuizSubmitRequest, db: Session = Depends(get_db)) -> QuizSubmitResponse:
    _get_or_create_user(db, payload.user_id)

    assessment: Assessment | None = assessment_agent.get_assessment(db, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail='Assessment not found')

    skill = _get_skill_or_404(db, assessment.skill_node_id)
    _assert_skill_unlocked_for_learning(db, user_id=payload.user_id, skill=skill)

    try:
        score, feedback, _attempt = assessment_agent.grade_assessment(
            db,
            assessment=assessment,
            user_id=payload.user_id,
            answers=payload.answers,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    updated_state = profile_agent.apply_quiz_score(db, payload.user_id, skill, score)
    _invalidate_recommendations(db, skill.topic_id, payload.user_id)

    return QuizSubmitResponse(
        score=round(score, 3),
        feedback=feedback,
        updated_mastery=round(updated_state.mastery, 3),
        updated_status=updated_state.status,
        updated_progress_state=updated_state.progress_state,  # type: ignore[arg-type]
    )


@router.post('/skills/{skill_id}/progress/update', response_model=MasteryUpdateResponse)
def update_progress(skill_id: int, payload: MasteryUpdateRequest, db: Session = Depends(get_db)) -> MasteryUpdateResponse:
    _get_or_create_user(db, payload.user_id)
    skill = _get_skill_or_404(db, skill_id)
    _assert_skill_unlocked_for_learning(db, user_id=payload.user_id, skill=skill)

    try:
        state = profile_agent.apply_progress_event(
            db,
            user_id=payload.user_id,
            skill_node=skill,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_recommendations(db, skill.topic_id, payload.user_id)

    return MasteryUpdateResponse(
        skill_node_id=skill_id,
        mastery=round(state.mastery, 3),
        status=state.status,
        progress_state=state.progress_state,  # type: ignore[arg-type]
    )


@router.post('/skills/{skill_id}/deep-dive', response_model=SkillTreeResponse)
async def create_deep_dive_branch(
    skill_id: int,
    payload: DeepDiveBranchRequest,
    db: Session = Depends(get_db),
) -> SkillTreeResponse:
    _get_or_create_user(db, payload.user_id)
    parent_skill = _get_skill_or_404(db, skill_id)
    topic = _get_topic_or_404(db, parent_skill.topic_id)
    if topic.user_id != payload.user_id:
        raise HTTPException(status_code=404, detail='Topic not found')

    _assert_skill_unlocked_for_learning(db, user_id=payload.user_id, skill=parent_skill)

    try:
        await skill_graph_agent.create_deep_dive_branch(
            db,
            topic=topic,
            parent_node=parent_skill,
            user_id=payload.user_id,
            focus=payload.focus.strip() or None,
            branch_size=payload.branch_size,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    profile_agent.ensure_states_for_topic(db, payload.user_id, topic.id)
    profile_agent.recompute_unlocks(db, payload.user_id, topic.id)
    _invalidate_recommendations(db, topic.id, payload.user_id)
    return _build_skill_tree_response(db, topic, payload.user_id)
