from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.course_preferences import ASSESSMENT_STYLE_TO_QUESTION_TYPE, ASSESSMENT_STYLE_VALUES


class SkillPlanNode(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=10, max_length=600)
    difficulty: int = Field(ge=1, le=5)
    prerequisites: list[str] = Field(default_factory=list)

    @field_validator('key')
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower().replace(' ', '_').replace('-', '_')


class SkillGraphPlan(BaseModel):
    nodes: list[SkillPlanNode] = Field(min_length=5, max_length=20)


class DeepDivePlanNode(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=10, max_length=600)
    difficulty: int = Field(ge=1, le=5)
    prerequisites: list[str] = Field(default_factory=list)

    @field_validator('key')
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower().replace(' ', '_').replace('-', '_')


class DeepDiveBranchPlan(BaseModel):
    branch_title: str = Field(min_length=4, max_length=180)
    rationale: str = Field(min_length=20, max_length=400)
    nodes: list[DeepDivePlanNode] = Field(min_length=2, max_length=6)


class BranchSuggestionPlanItem(BaseModel):
    title: str = Field(min_length=4, max_length=160)
    focus: str = Field(min_length=3, max_length=180)
    rationale: str = Field(min_length=20, max_length=320)
    purpose: Literal['enrichment', 'remediation', 'specialization', 'exploration', 'assessment_prep', 'project']


class BranchSuggestionPlan(BaseModel):
    suggestions: list[BranchSuggestionPlanItem] = Field(min_length=1, max_length=4)


class RecommendationChoice(BaseModel):
    skill_node_id: int
    action_type: Literal['study_generated', 'study_external', 'practice_quiz']
    rationale: str = Field(min_length=15, max_length=400)
    confidence: float = Field(ge=0.0, le=1.0)


class RecommendationPlan(BaseModel):
    recommendations: list[RecommendationChoice] = Field(min_length=1, max_length=5)


class QuizQuestionPlan(BaseModel):
    id: str
    prompt: str = Field(min_length=8, max_length=500)
    choices: list[str] = Field(min_length=4, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=8, max_length=400)


class QuizPlan(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    questions: list[QuizQuestionPlan] = Field(min_length=1, max_length=10)


class ExternalResourceReason(BaseModel):
    url: str
    relevance_reason: str = Field(min_length=10, max_length=280)


class ExternalResourceReasoningPlan(BaseModel):
    resources: list[ExternalResourceReason] = Field(min_length=1, max_length=10)


class LessonKeyConcept(BaseModel):
    term: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=260)


class LessonSection(BaseModel):
    heading: str = Field(min_length=2, max_length=140)
    content: str = Field(min_length=20, max_length=800)


class LessonPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    summary: str = Field(min_length=20, max_length=300)
    learning_objectives: list[str] = Field(min_length=2, max_length=6)
    key_concepts: list[LessonKeyConcept] = Field(min_length=2, max_length=8)
    sections: list[LessonSection] = Field(min_length=2, max_length=8)
    takeaways: list[str] = Field(min_length=2, max_length=6)
    next_steps: list[str] = Field(min_length=1, max_length=4)


class ExamplePlanItem(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    explanation: str = Field(min_length=20, max_length=500)
    why_it_matters: str = Field(min_length=15, max_length=280)


class ExamplesPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    intro: str = Field(min_length=20, max_length=420)
    examples: list[ExamplePlanItem] = Field(min_length=2, max_length=6)


class ExercisePlanItem(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    task: str = Field(min_length=20, max_length=500)
    hints: list[str] = Field(min_length=1, max_length=4)
    expected_outcome: str = Field(min_length=15, max_length=300)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'


class ExercisesPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    intro: str = Field(min_length=20, max_length=420)
    exercises: list[ExercisePlanItem] = Field(min_length=2, max_length=8)


class TutorReplyPlan(BaseModel):
    overview: str = Field(min_length=20, max_length=500)
    key_points: list[str] = Field(min_length=2, max_length=6)
    practical_steps: list[str] = Field(min_length=2, max_length=6)
    pitfalls: list[str] = Field(default_factory=list, max_length=4)
    next_step: str = Field(min_length=10, max_length=240)


class TopicRelevancePlan(BaseModel):
    relevance: Literal['relevant', 'related', 'unrelated']
    rationale: str = Field(min_length=10, max_length=280)


AssessmentQuestionTypeLiteral = Literal[
    'multiple_choice',
    'short_answer',
    'explain',
    'scenario',
    'error_spotting',
    'reflection',
]

AssessmentStyleLiteral = Literal[
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


class AssessmentRubricCriterion(BaseModel):
    concept: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=8, max_length=220)
    weight: float = Field(ge=0.0, le=1.0)


class AssessmentQuestionPlanItem(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    assessment_style: AssessmentStyleLiteral
    question_type: AssessmentQuestionTypeLiteral
    prompt: str = Field(min_length=10, max_length=700)
    choices: list[str] | None = None
    answer_index: int | None = None
    model_answer: str = Field(min_length=12, max_length=2600)
    hints: list[str] = Field(default_factory=list, max_length=4)
    expected_concepts: list[str] = Field(default_factory=list, max_length=8)
    rubric: list[AssessmentRubricCriterion] = Field(default_factory=list, max_length=8)
    difficulty: int = Field(ge=1, le=5)
    confidence_prompt: str = Field(default='How confident are you in your answer?', max_length=120)

    @model_validator(mode='after')
    def validate_by_type(self) -> 'AssessmentQuestionPlanItem':
        if self.assessment_style not in ASSESSMENT_STYLE_VALUES:
            raise ValueError('assessment_style is not supported.')
        expected_type = ASSESSMENT_STYLE_TO_QUESTION_TYPE[self.assessment_style]
        if self.question_type != expected_type and self.question_type != 'reflection':
            self.question_type = expected_type  # type: ignore[assignment]

        normalized_concepts = [item.strip() for item in self.expected_concepts if item and item.strip()]
        rubric_concepts = [criterion.concept.strip() for criterion in self.rubric if criterion.concept.strip()]
        if not normalized_concepts and rubric_concepts:
            normalized_concepts = rubric_concepts[:4]
        self.expected_concepts = list(dict.fromkeys(normalized_concepts))[:8]

        if self.question_type == 'multiple_choice':
            if not self.choices or len(self.choices) != 4:
                raise ValueError('multiple_choice questions must include exactly 4 choices.')
            if self.answer_index is None or self.answer_index < 0 or self.answer_index > 3:
                raise ValueError('multiple_choice questions must include answer_index between 0 and 3.')
            if len(self.model_answer.strip()) < 12:
                raise ValueError('multiple_choice questions must include a concrete model_answer.')
            return self

        self.answer_index = None
        if self.choices:
            self.choices = [str(item).strip() for item in self.choices if str(item).strip()]
            if len(self.choices) == 0:
                self.choices = None

        if self.question_type == 'reflection':
            self.expected_concepts = []
            return self

        if len(self.expected_concepts) == 0:
            raise ValueError('expected_concepts must include at least one concept for non-reflection questions.')
        if len(self.model_answer.strip()) < 12:
            raise ValueError('model_answer must be provided for non-reflection questions.')
        return self

    @model_validator(mode='after')
    def ensure_rubric_for_open_questions(self) -> 'AssessmentQuestionPlanItem':
        if self.question_type in {'short_answer', 'explain', 'scenario', 'error_spotting'} and len(self.rubric) == 0:
            self.rubric = [
                AssessmentRubricCriterion(
                    concept=concept,
                    description=f'Addresses {concept} accurately and applies it to the prompt.',
                    weight=1.0 / max(1, len(self.expected_concepts)),
                )
                for concept in self.expected_concepts[:3]
            ]
        if self.question_type == 'reflection':
            self.answer_index = None
            self.choices = None
        if not self.hints:
            self.hints = ['Focus on the core concept before adding detail.']
        return self


class AssessmentPlan(BaseModel):
    title: str = Field(min_length=4, max_length=220)
    instructions: str = Field(min_length=20, max_length=380)
    difficulty: int = Field(ge=1, le=5)
    target_level: Literal['beginner', 'intermediate', 'advanced']
    questions: list[AssessmentQuestionPlanItem] = Field(min_length=4, max_length=12)


class AssessmentQuestionEvaluation(BaseModel):
    question_id: str = Field(min_length=1, max_length=40)
    score: float = Field(ge=0.0, le=1.0)
    feedback: str = Field(min_length=12, max_length=500)
    strengths: list[str] = Field(default_factory=list, max_length=4)
    missing_concepts: list[str] = Field(default_factory=list, max_length=6)


class AssessmentEvaluationPlan(BaseModel):
    question_feedback: list[AssessmentQuestionEvaluation] = Field(min_length=1, max_length=12)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    weaknesses: list[str] = Field(default_factory=list, max_length=6)
    review_next: str = Field(min_length=12, max_length=320)
    recommended_follow_up: str = Field(min_length=12, max_length=320)
    summary: str = Field(min_length=12, max_length=500)
