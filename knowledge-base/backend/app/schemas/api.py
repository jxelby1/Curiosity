from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.course_preferences import (
    ASSESSMENT_STYLE_VALUES,
    DEFAULT_ASSESSMENT_STYLES,
)
from app.db.models import AssessmentQuestionType, NoteType, ResourceType, SkillStatus


class TopicCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=500)
    goal: str = Field(default='', max_length=500)
    course_depth: Literal['light', 'standard', 'deep_dive'] = 'standard'
    starting_skill_level: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'
    assessment_styles: list[
        Literal[
            'open_text',
            'short_answer',
            'multiple_choice',
            'flashcard',
            'scenario',
            'coding',
            'debugging',
            'code_completion',
            'code_interpretation',
            'math_problem',
        ]
    ] = Field(default_factory=lambda: DEFAULT_ASSESSMENT_STYLES.copy(), max_length=10)

    @model_validator(mode='after')
    def ensure_assessment_styles(self) -> 'TopicCreateRequest':
        deduped = []
        seen: set[str] = set()
        for style in self.assessment_styles:
            if style in seen:
                continue
            seen.add(style)
            deduped.append(style)
        self.assessment_styles = deduped or DEFAULT_ASSESSMENT_STYLES.copy()
        return self


class TopicResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str
    goal: str
    course_depth: Literal['light', 'standard', 'deep_dive'] = 'standard'
    starting_skill_level: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'
    assessment_styles: list[
        Literal[
            'open_text',
            'short_answer',
            'multiple_choice',
            'flashcard',
            'scenario',
            'coding',
            'debugging',
            'code_completion',
            'code_interpretation',
            'math_problem',
        ]
    ] = Field(default_factory=lambda: DEFAULT_ASSESSMENT_STYLES.copy())
    created_at: datetime


class TopicListResponse(BaseModel):
    topics: list[TopicResponse]


class TopicInitializationStatusResponse(BaseModel):
    topic_id: int
    status: Literal['queued', 'running', 'ready', 'preloading', 'completed', 'failed']
    current_step: str
    progress: float = Field(ge=0.0, le=1.0)
    ready_for_entry: bool = False
    background_complete: bool = False
    first_ready_skill_id: int | None = None
    status_messages: list[str] = Field(default_factory=list)
    error_text: str = ''
    started_at: datetime | None = None
    ready_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class TopicInitializationResponse(BaseModel):
    topic: TopicResponse
    initialization: TopicInitializationStatusResponse


class SkillNodeResponse(BaseModel):
    id: int
    topic_id: int
    name: str
    description: str
    difficulty: int
    node_kind: Literal['core', 'optional_branch'] = 'core'
    branch_origin: str = 'core'
    branch_purpose: str = 'core_curriculum'
    branch_depth: int = 0
    branch_parent_skill_id: int | None = None
    mastery_estimate: float
    status: SkillStatus
    force_unlocked: bool = False
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
    focus: str = Field(default='', max_length=240)
    branch_size: int = Field(default=3, ge=2, le=5)
    purpose: Literal['exploration', 'specialization', 'enrichment', 'remediation', 'assessment_prep', 'project'] = 'exploration'


class BranchSuggestionGenerateRequest(BaseModel):
    limit: int = Field(default=2, ge=1, le=3)
    trigger_event: Literal['manual', 'assessment_performance', 'completion', 'interest'] = 'manual'


class BranchSuggestionResponse(BaseModel):
    id: int
    topic_id: int
    parent_skill_id: int
    title: str
    focus: str
    rationale: str
    purpose: str
    origin: str
    status: str
    accepted_branch_root_skill_id: int | None = None
    created_at: datetime
    updated_at: datetime


class BranchSuggestionListResponse(BaseModel):
    suggestions: list[BranchSuggestionResponse] = Field(default_factory=list)


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


class SaveTutorResponseToNoteRequest(BaseModel):
    mode: Literal['full', 'excerpt', 'summary'] = 'full'
    title: str = Field(default='', max_length=120)
    body: str = Field(default='', max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    note_type: NoteType = NoteType.summary
    skill_node_id: int | None = None


class AppendTutorResponseToNoteRequest(BaseModel):
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
    num_questions: int = Field(default=6, ge=1, le=10)


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
    answers: list[int]


class QuizSubmitResponse(BaseModel):
    score: float
    feedback: list[dict[str, Any]]
    updated_mastery: float
    updated_status: SkillStatus
    updated_progress_state: Literal['not_started', 'learning', 'completed', 'verified']


class MasteryUpdateRequest(BaseModel):
    action: Literal['complete_lesson', 'complete_exercises']


class MasteryUpdateResponse(BaseModel):
    skill_node_id: int
    mastery: float
    status: SkillStatus
    progress_state: Literal['not_started', 'learning', 'completed', 'verified']


class AssessmentGenerateRequest(BaseModel):
    topic_id: int
    skill_node_id: int
    question_count: int | None = Field(default=None, ge=4, le=10)
    regenerate: bool = False
    assessment_styles: list[str] | None = None

    @model_validator(mode='after')
    def validate_styles(self) -> 'AssessmentGenerateRequest':
        if self.assessment_styles is None:
            return self
        normalized = []
        seen: set[str] = set()
        for style in self.assessment_styles:
            if style not in ASSESSMENT_STYLE_VALUES:
                continue
            if style in seen:
                continue
            seen.add(style)
            normalized.append(style)
        self.assessment_styles = normalized
        return self


class AssessmentQuestionResponse(BaseModel):
    id: int
    question_type: AssessmentQuestionType
    assessment_style: str
    prompt: str
    choices: list[str] = Field(default_factory=list)
    expected_concepts: list[str] = Field(default_factory=list)
    rubric: dict[str, Any] = Field(default_factory=dict)
    difficulty: int
    order_index: int


class AssessmentDetailResponse(BaseModel):
    id: int
    topic_id: int
    skill_node_id: int
    title: str
    difficulty: int
    target_level: str
    question_mix: dict[str, int]
    version: int
    source: Literal['stored', 'generated', 'regenerated']
    answers_revealed: bool = False
    mastery_eligible: bool = True
    questions: list[AssessmentQuestionResponse]
    created_at: datetime


class AssessmentRevealQuestionResponse(BaseModel):
    question_id: int
    question_type: AssessmentQuestionType
    assessment_style: str = ''
    answer: str
    key_points: list[str] = Field(default_factory=list)


class AssessmentRevealResponse(BaseModel):
    assessment_id: int
    answers_revealed: bool
    mastery_eligible: bool
    warning: str
    question_reveals: list[AssessmentRevealQuestionResponse] = Field(default_factory=list)


class AssessmentResponseInput(BaseModel):
    question_id: int
    selected_option_index: int | None = None
    answer_text: str | None = Field(default=None, max_length=4000)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode='after')
    def ensure_answer(self) -> 'AssessmentResponseInput':
        if self.selected_option_index is None and not (self.answer_text or '').strip():
            raise ValueError('Provide selected_option_index or answer_text.')
        return self


class AssessmentSubmitRequest(BaseModel):
    responses: list[AssessmentResponseInput] = Field(min_length=1, max_length=12)


class AssessmentQuestionFeedbackResponse(BaseModel):
    question_id: int
    question_type: AssessmentQuestionType
    assessment_style: str = ''
    score: float | None = None
    confidence_score: float | None = None
    feedback: str
    missing_concepts: list[str] = Field(default_factory=list)


class AssessmentSubmitResponse(BaseModel):
    assessment_id: int
    attempt_id: int
    score: float
    confidence_avg: float
    mastery_delta: float
    mastery_eligible: bool = True
    mastery_applied: bool = True
    practice_mode: bool = False
    outcome_message: str = ''
    feedback: list[AssessmentQuestionFeedbackResponse]
    strengths: list[str]
    weaknesses: list[str]
    review_next: str
    recommended_follow_up: str
    summary: str
    updated_mastery: float
    updated_status: SkillStatus
    updated_progress_state: Literal['not_started', 'learning', 'completed', 'verified']
    unlocked_skill_ids: list[int] = Field(default_factory=list)


class AssessmentAttemptResponse(BaseModel):
    id: int
    assessment_id: int
    user_id: int
    score: float
    confidence_avg: float
    mastery_delta: float
    mastery_eligible: bool = True
    practice_mode: bool = False
    strengths: list[str]
    weaknesses: list[str]
    review_next: str
    recommended_follow_up: str
    feedback: list[AssessmentQuestionFeedbackResponse]
    created_at: datetime


class TopicProgressNode(BaseModel):
    skill_node_id: int
    name: str
    status: SkillStatus
    progress_state: Literal['not_started', 'learning', 'completed', 'verified']
    mastery: float
    best_quiz_score: float
    recommended_next_action: str


class TopicProgressResponse(BaseModel):
    topic_id: int
    topic_name: str
    total_nodes: int
    verified_nodes: int
    available_nodes: int
    mastery_average: float
    tree_stage: int = Field(ge=1, le=6)
    nodes: list[TopicProgressNode]


class UserTopicProgressSummary(BaseModel):
    topic_id: int
    topic_name: str
    total_nodes: int
    verified_nodes: int
    mastery_average: float
    tree_stage: int = Field(ge=1, le=6)


class UserProgressSummaryResponse(BaseModel):
    user_id: int
    xp: int
    level: int
    topics_total: int
    verified_nodes_total: int
    mastery_average: float
    topics: list[UserTopicProgressSummary]


class TopicActionItem(BaseModel):
    skill_node_id: int | None = None
    skill_name: str
    action_type: str
    title: str
    description: str
    tab: Literal['overview', 'lesson', 'examples', 'exercises', 'quiz', 'resources'] = 'overview'


class UnlockAnticipationResponse(BaseModel):
    skill_node_id: int
    skill_name: str
    status_label: str
    why_locked: str
    steps: list[str] = Field(default_factory=list)
    next_step_skill_node_id: int | None = None
    next_step_tab: Literal['overview', 'lesson', 'examples', 'exercises', 'quiz', 'resources'] = 'overview'


class TopicReminderResponse(BaseModel):
    id: int
    reminder_type: str
    title: str
    message: str
    action_skill_node_id: int | None = None
    action_tab: Literal['overview', 'lesson', 'examples', 'exercises', 'quiz', 'resources'] = 'overview'
    created_at: datetime


class MilestoneEventResponse(BaseModel):
    id: int
    milestone_type: str
    title: str
    message: str
    skill_node_id: int | None = None
    created_at: datetime


class TopicRetentionLoopResponse(BaseModel):
    topic_id: int
    topic_name: str
    cadence: Literal['daily', 'weekly']
    plan_summary: str
    next_actions: list[TopicActionItem] = Field(default_factory=list)
    learning_plan: list[TopicActionItem] = Field(default_factory=list)
    unlock_anticipation: UnlockAnticipationResponse | None = None
    reminder: TopicReminderResponse | None = None
    milestones: list[MilestoneEventResponse] = Field(default_factory=list)
    total_nodes: int
    available_nodes: int
    verified_nodes: int
    completed_nodes: int
    lessons_completed: int
    assessments_taken: int
    mastery_average: float
    tree_stage: int = Field(ge=1, le=6)
    streak_days: int = 0
    activity_days_last_14: int = 0
    latest_activity_at: datetime | None = None
    dev_unlock_enabled: bool = False
