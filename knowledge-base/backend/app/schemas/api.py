from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from app.db.models import NoteType, ResourceType, SkillStatus


class TopicCreateRequest(BaseModel):
    user_id: int = 1
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=500)
    goal: str = Field(default='', max_length=500)


class TopicResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str
    goal: str
    created_at: datetime


class TopicListResponse(BaseModel):
    topics: list[TopicResponse]


class SkillNodeResponse(BaseModel):
    id: int
    topic_id: int
    name: str
    description: str
    difficulty: int
    node_kind: Literal['core', 'optional_branch'] = 'core'
    branch_parent_skill_id: int | None = None
    mastery_estimate: float
    status: SkillStatus
    lock_reason: str | None = None
    progress_state: Literal['not_started', 'learning', 'completed', 'verified'] = 'not_started'
    lesson_completed: bool = False
    exercises_completed: bool = False
    quiz_taken: bool = False
    best_quiz_score: float | None = None
    prerequisites: list[int] = Field(default_factory=list)
    children: list[int] = Field(default_factory=list)
    recommended_next_action: str


class SkillTreeResponse(BaseModel):
    topic: TopicResponse
    nodes: list[SkillNodeResponse]


class DeepDiveBranchRequest(BaseModel):
    user_id: int = 1
    focus: str = Field(default='', max_length=240)
    branch_size: int = Field(default=3, ge=2, le=5)


class DocumentUploadResponse(BaseModel):
    document_id: int
    filename: str
    chunks_created: int


class DocumentItemResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentItemResponse]


class NoteCreateRequest(BaseModel):
    title: str = Field(default='', max_length=120)
    body: str = Field(min_length=1, max_length=8000)
    note_type: NoteType = NoteType.personal
    skill_node_id: int | None = None
    tags: list[str] = Field(default_factory=list, max_length=12)


class NoteUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    body: str | None = Field(default=None, max_length=8000)
    note_type: NoteType | None = None
    skill_node_id: int | None = None
    tags: list[str] | None = Field(default=None, max_length=12)


class NoteResponse(BaseModel):
    id: int
    user_id: int
    topic_id: int
    skill_node_id: int | None = None
    note_type: NoteType
    tags: list[str] = Field(default_factory=list)
    source_type: Literal['user_authored', 'tutor_generated', 'external_resource'] = 'user_authored'
    source_chat_session_id: int | None = None
    source_message_id: int | None = None
    created_from_skill_node_id: int | None = None
    created_from_topic_id: int | None = None
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    notes: list[NoteResponse]


class ChatRequest(BaseModel):
    user_id: int = 1
    session_id: int | None = None
    skill_node_id: int | None = None
    include_personal_notes: bool = False
    include_web_resources: bool = False
    message: str = Field(min_length=1, max_length=600)


class TutorStructuredResponse(BaseModel):
    overview: str
    key_points: list[str] = Field(default_factory=list)
    practical_steps: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    next_step: str


class ChatContextUsage(BaseModel):
    document_chunks: int = 0
    personal_notes: int = 0
    external_resources: int = 0


class ChatCitation(BaseModel):
    title: str
    url: str
    snippet: str = ''


class ChatResponse(BaseModel):
    session_id: int
    assistant_message_id: int
    answer: str
    used_chunks: list[str]
    citations: list[ChatCitation] = Field(default_factory=list)
    structured_answer: TutorStructuredResponse | None = None
    context_usage: ChatContextUsage


class TutorSaveMode(BaseModel):
    mode: Literal['full', 'excerpt', 'summary'] = 'full'


class SaveTutorResponseToNoteRequest(BaseModel):
    user_id: int = 1
    mode: Literal['full', 'excerpt', 'summary'] = 'full'
    title: str = Field(default='', max_length=120)
    body: str = Field(default='', max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    note_type: NoteType = NoteType.summary
    skill_node_id: int | None = None


class AppendTutorResponseToNoteRequest(BaseModel):
    user_id: int = 1
    session_id: int
    message_id: int
    mode: Literal['full', 'excerpt', 'summary'] = 'excerpt'
    body: str = Field(default='', max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=12)


class TutorNoteSaveResponse(BaseModel):
    note: NoteResponse
    duplicate_warning: str | None = None
    appended: bool = False


class RecommendationItem(BaseModel):
    skill_node_id: int
    skill_name: str
    rationale: str
    action_type: str
    resource_mode: Literal['generated', 'external']
    confidence: float


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]


class GenerateResourceRequest(BaseModel):
    user_id: int = 1
    kind: Literal['lesson', 'examples', 'exercises']


class ResourceResponse(BaseModel):
    id: int
    skill_node_id: int
    resource_type: ResourceType
    title: str
    url: str
    summary: str
    content: str
    structured_content: dict[str, Any] | None = None
    source: Literal['stored', 'generated', 'regenerated']
    version: int
    relevance_reason: str


class ExternalResourceItem(BaseModel):
    id: int
    title: str
    url: str
    summary: str
    resource_type: ResourceType
    relevance_reason: str


class ExternalResourceResponse(BaseModel):
    resources: list[ExternalResourceItem]


class QuizGenerateRequest(BaseModel):
    user_id: int = 1
    num_questions: int = Field(default=3, ge=1, le=10)


class QuizQuestion(BaseModel):
    id: str
    prompt: str
    choices: list[str]


class QuizResponse(BaseModel):
    assessment_id: int
    title: str
    questions: list[QuizQuestion]
    source: Literal['stored', 'generated', 'regenerated']
    version: int


class QuizSubmitRequest(BaseModel):
    user_id: int = 1
    answers: list[int]


class QuizSubmitResponse(BaseModel):
    score: float
    feedback: list[dict]
    updated_mastery: float
    updated_status: SkillStatus
    updated_progress_state: Literal['not_started', 'learning', 'completed', 'verified']


class MasteryUpdateRequest(BaseModel):
    user_id: int = 1
    action: Literal['complete_lesson', 'complete_exercises']


class MasteryUpdateResponse(BaseModel):
    skill_node_id: int
    mastery: float
    status: SkillStatus
    progress_state: Literal['not_started', 'learning', 'completed', 'verified']
