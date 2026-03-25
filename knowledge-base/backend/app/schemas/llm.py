from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
