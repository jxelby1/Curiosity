from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
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
from app.db.models import Assessment, Document, SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState
from app.schemas.api import (
    ChatRequest,
    ChatResponse,
    ExternalResourceItem,
    ExternalResourceResponse,
    GenerateResourceRequest,
    MasteryUpdateRequest,
    MasteryUpdateResponse,
    NoteItemResponse,
    NoteListResponse,
    NoteUploadResponse,
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
tutor_agent = TutorAgent(llm_service, retrieval_service)
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


def _build_skill_tree_response(db: Session, topic: Topic, user_id: int) -> SkillTreeResponse:
    nodes = db.scalars(select(SkillNode).where(SkillNode.topic_id == topic.id)).all()
    edges = db.scalars(select(SkillEdge).where(SkillEdge.topic_id == topic.id)).all()

    prereq_map: dict[int, list[int]] = {}
    child_map: dict[int, list[int]] = {}
    for edge in edges:
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

        payload_nodes.append(
            SkillNodeResponse(
                id=node.id,
                topic_id=node.topic_id,
                name=node.name,
                description=node.description,
                difficulty=node.difficulty,
                mastery_estimate=round(float(mastery), 3),
                status=node_status,
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

    payload_nodes.sort(key=lambda item: (item.difficulty, item.id))
    return SkillTreeResponse(topic=_topic_to_response(topic), nodes=payload_nodes)


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
    return _build_skill_tree_response(db, topic, user_id)


@router.get('/topics/{topic_id}/skill-tree', response_model=SkillTreeResponse)
def get_skill_tree(topic_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> SkillTreeResponse:
    _get_or_create_user(db, user_id)
    topic = _get_topic_or_404(db, topic_id)
    return _build_skill_tree_response(db, topic, user_id)


@router.post('/topics/{topic_id}/notes/upload', response_model=NoteUploadResponse)
async def upload_notes(
    topic_id: int,
    user_id: int = Form(default=1),
    raw_text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> NoteUploadResponse:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)

    text = (raw_text or '').strip()
    filename = 'pasted-note.txt'
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

    return NoteUploadResponse(document_id=doc.id, filename=doc.filename, chunks_created=chunks)


@router.get('/topics/{topic_id}/notes', response_model=NoteListResponse)
def list_notes(topic_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> NoteListResponse:
    _get_or_create_user(db, user_id)
    _get_topic_or_404(db, topic_id)

    docs = db.scalars(
        select(Document)
        .where(Document.topic_id == topic_id, Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    ).all()

    return NoteListResponse(
        documents=[
            NoteItemResponse(
                id=doc.id,
                filename=doc.filename,
                content_type=doc.content_type,
                created_at=doc.created_at,
            )
            for doc in docs
        ]
    )


@router.post('/topics/{topic_id}/chat', response_model=ChatResponse)
async def chat(topic_id: int, payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    _get_or_create_user(db, payload.user_id)
    topic = _get_topic_or_404(db, topic_id)

    try:
        session_id, answer, used_chunks = await tutor_agent.respond(
            db,
            topic=topic,
            user_id=payload.user_id,
            message=payload.message,
            session_id=payload.session_id,
            skill_node_id=payload.skill_node_id,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    return ChatResponse(session_id=session_id, answer=answer, used_chunks=used_chunks)


@router.get('/topics/{topic_id}/recommendations', response_model=RecommendationResponse)
async def get_recommendations(topic_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)) -> RecommendationResponse:
    _get_or_create_user(db, user_id)
    topic = _get_topic_or_404(db, topic_id)

    profile_agent.ensure_states_for_topic(db, user_id, topic_id)
    profile_agent.recompute_unlocks(db, user_id, topic_id)

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

    try:
        score, feedback, _attempt = assessment_agent.grade_assessment(
            db,
            assessment=assessment,
            user_id=payload.user_id,
            answers=payload.answers,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_service_error(exc)

    skill = _get_skill_or_404(db, assessment.skill_node_id)
    updated_state = profile_agent.apply_quiz_score(db, payload.user_id, skill, score)

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

    try:
        state = profile_agent.apply_progress_event(
            db,
            user_id=payload.user_id,
            skill_node=skill,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MasteryUpdateResponse(
        skill_node_id=skill_id,
        mastery=round(state.mastery, 3),
        status=state.status,
        progress_state=state.progress_state,  # type: ignore[arg-type]
    )
