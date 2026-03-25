from __future__ import annotations

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from app.db.models import ResourceType, SkillStatus


class TopicCreateRequest(BaseModel):
    user_id: int = 1
    name: str
    description: str = ''
    goal: str = ''


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
    mastery_estimate: float
    status: SkillStatus
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


class NoteUploadResponse(BaseModel):
    document_id: int
    filename: str
    chunks_created: int


class NoteItemResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    created_at: datetime


class NoteListResponse(BaseModel):
    documents: list[NoteItemResponse]


class ChatRequest(BaseModel):
    user_id: int = 1
    session_id: int | None = None
    skill_node_id: int | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    used_chunks: list[str]


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
