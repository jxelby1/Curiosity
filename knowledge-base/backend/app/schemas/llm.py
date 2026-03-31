from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.branching import normalize_branch_purpose
from app.core.course_preferences import ASSESSMENT_STYLE_TO_QUESTION_TYPE, ASSESSMENT_STYLE_VALUES


_PEDAGOGY_EVIDENCE_HINTS = (
    'for example',
    'for instance',
    'such as',
    'consider ',
    'look at ',
    'take ',
    'imagine ',
    'one concrete example',
    'a concrete example',
    'in this scene',
    'in the passage',
    'in this passage',
    'in the sentence',
    'in this sentence',
    'in the experiment',
    'in this experiment',
    'in the policy',
    'in this policy',
    'the data shows',
    'the data reveal',
)
_PEDAGOGY_EVIDENCE_OBJECT_HINTS = (
    'scene',
    'passage',
    'policy',
    'experiment',
    'sentence',
    'equation',
    'artifact',
    'data',
    'document',
    'diagram',
    'map',
)
_PEDAGOGY_NEGATED_EVIDENCE_HINTS = (
    'without evidence',
    'without further evidence',
    'no evidence',
    'no concrete example',
    'no concrete case',
    'has not been taught yet',
    'not been taught yet',
)
_PEDAGOGY_REASONING_HINTS = (
    'because',
    'therefore',
    'which means',
    'so that',
    'this matters because',
    'as a result',
    'in practice',
    'which changes',
)
_PEDAGOGY_COMPARISON_HINTS = (
    'compare',
    'contrast',
    'whereas',
    'unlike',
    'by contrast',
    'in contrast',
    'similar',
    'different',
    'variation',
)
_PEDAGOGY_TRANSFER_HINTS = (
    'apply',
    'try',
    'use this',
    'practice',
    'response',
    'draft',
    'solve',
    'test',
    'write',
    'make',
)
_ASSUMED_FAMILIARITY_HINTS = (
    'as you already know',
    'as discussed above',
    'as we saw earlier',
    'if you know',
    'if you have seen',
    'if you have read',
    'if you are familiar',
    'already familiar',
)
_GENERIC_EXAMPLE_NAME_PATTERN = re.compile(r'^(example|case study|sample|scenario)\s*(?:[0-9]+|[a-z])?$', re.IGNORECASE)


def _pedagogy_blob(parts: list[str]) -> str:
    return ' '.join(' '.join(str(part or '').split()) for part in parts if str(part or '').strip()).lower()


def _contains_hint(blob: str, hints: tuple[str, ...]) -> bool:
    lowered = (blob or '').lower()
    return any(hint in lowered for hint in hints)


def _has_pedagogy_evidence(blob: str) -> bool:
    lowered = (blob or '').lower()
    strong_hits = sum(1 for hint in _PEDAGOGY_EVIDENCE_HINTS if hint in lowered)
    object_hits = sum(
        1 for hint in _PEDAGOGY_EVIDENCE_OBJECT_HINTS if re.search(rf'\b{re.escape(hint)}s?\b', lowered)
    )
    negated = any(hint in lowered for hint in _PEDAGOGY_NEGATED_EVIDENCE_HINTS)
    if strong_hits >= 1:
        return True
    if object_hits >= 2 and not negated:
        return True
    return False


def _normalize_prerequisite_keys(value: object) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = [str(value)]

    normalized: list[str] = []
    for item in raw_values:
        token = str(item).strip().lower().replace(' ', '_').replace('-', '_')
        if not token or token in normalized:
            continue
        normalized.append(token)
        if len(normalized) >= 2:
            break
    return normalized


def _normalize_instructional_role_value(raw_role: object, *, fallback: str = 'enrichment') -> str:
    normalized = str(raw_role or '').strip().lower().replace(' ', '_').replace('-', '_')
    alias = {
        'foundation': 'foundational_concept',
        'foundational': 'foundational_concept',
        'bridge': 'conceptual_bridge',
        'application': 'practical_application',
        'case_study': 'case_deepening',
        'comparison': 'comparison_contrast',
        'assessment_prep': 'assessment_preparation',
        'review': 'synthesis_review',
        'synthesis': 'synthesis_review',
        'remedial': 'remediation',
        'exploration': 'enrichment',
        'deepen_theme': 'enrichment',
        'compare_contrast': 'comparison_contrast',
        'context_influence': 'conceptual_bridge',
        'study_exemplar': 'case_deepening',
        'creative_response': 'practical_application',
        'style_technique_practice': 'remediation',
        'follow_lineage': 'synthesis_review',
    }
    return alias.get(normalized, normalized or fallback)


class SkillPlanNode(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=10, max_length=600)
    instructional_role: Literal[
        'foundational_concept',
        'conceptual_bridge',
        'practical_application',
        'case_deepening',
        'comparison_contrast',
        'assessment_preparation',
        'synthesis_review',
        'remediation',
        'enrichment',
        'specialization',
    ] = 'foundational_concept'
    difficulty: int = Field(ge=1, le=5)
    prerequisites: list[str] = Field(default_factory=list, max_length=2)

    @field_validator('key')
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower().replace(' ', '_').replace('-', '_')

    @field_validator('prerequisites', mode='before')
    @classmethod
    def normalize_prerequisites(cls, value: object) -> list[str]:
        return _normalize_prerequisite_keys(value)


class SkillGraphPlan(BaseModel):
    nodes: list[SkillPlanNode] = Field(min_length=5, max_length=20)


class SkillNodeTitleRewrite(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=3, max_length=120)

    @field_validator('key')
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower().replace(' ', '_').replace('-', '_')


class SkillNodeTitleRewritePlan(BaseModel):
    nodes: list[SkillNodeTitleRewrite] = Field(min_length=1, max_length=24)


class DeepDivePlanNode(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=10, max_length=600)
    instructional_role: Literal[
        'practical_application',
        'case_deepening',
        'comparison_contrast',
        'assessment_preparation',
        'synthesis_review',
        'remediation',
        'enrichment',
        'specialization',
    ] = 'enrichment'
    difficulty: int = Field(ge=1, le=5)
    prerequisites: list[str] = Field(default_factory=list, max_length=2)

    @field_validator('key')
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower().replace(' ', '_').replace('-', '_')

    @field_validator('instructional_role', mode='before')
    @classmethod
    def normalize_instructional_role(cls, value: object) -> str:
        return _normalize_instructional_role_value(value, fallback='enrichment')

    @field_validator('prerequisites', mode='before')
    @classmethod
    def normalize_prerequisites(cls, value: object) -> list[str]:
        return _normalize_prerequisite_keys(value)


class DeepDiveBranchPlan(BaseModel):
    branch_title: str = Field(min_length=4, max_length=180)
    rationale: str = Field(min_length=20, max_length=400)
    nodes: list[DeepDivePlanNode] = Field(min_length=1, max_length=6)

    @field_validator('rationale', mode='before')
    @classmethod
    def normalize_rationale_length(cls, value: object) -> str:
        text = ' '.join(str(value or '').split()).strip()
        if len(text) <= 400:
            return text
        trimmed = text[:399].rstrip(' ,;:-')
        if not trimmed:
            trimmed = text[:399].rstrip()
        return f'{trimmed}…'


class BranchSuggestionPlanItem(BaseModel):
    title: str = Field(min_length=4, max_length=160)
    focus: str = Field(min_length=3, max_length=180)
    rationale: str = Field(min_length=20, max_length=320)
    purpose: Literal[
        'deepen_theme',
        'compare_contrast',
        'context_influence',
        'study_exemplar',
        'creative_response',
        'style_technique_practice',
        'follow_lineage',
        'enrichment',
        'remediation',
        'specialization',
        'exploration',
        'assessment_prep',
        'project',
        'curiosity',
    ]

    @field_validator('purpose', mode='before')
    @classmethod
    def normalize_purpose(cls, value: object) -> str:
        return normalize_branch_purpose(str(value or ''))

    @field_validator('title', 'focus', mode='before')
    @classmethod
    def normalize_text_fields(cls, value: object) -> str:
        return ' '.join(str(value or '').split()).strip()

    @field_validator('rationale', mode='before')
    @classmethod
    def normalize_rationale(cls, value: object) -> str:
        text = ' '.join(str(value or '').split()).strip()
        if len(text) <= 320:
            return text
        trimmed = text[:319].rstrip(' ,;:-')
        if not trimmed:
            trimmed = text[:319].rstrip()
        return f'{trimmed}…'


class BranchSuggestionPlan(BaseModel):
    suggestions: list[BranchSuggestionPlanItem] = Field(min_length=1, max_length=1)


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
    role: Literal['core_concept', 'context', 'example', 'analysis', 'comparison', 'transfer']
    heading: str = Field(min_length=2, max_length=140)
    content: str = Field(min_length=80, max_length=800)


class LessonPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    summary: str = Field(min_length=20, max_length=300)
    learning_objectives: list[str] = Field(min_length=2, max_length=6)
    key_concepts: list[LessonKeyConcept] = Field(min_length=3, max_length=8)
    sections: list[LessonSection] = Field(min_length=3, max_length=8)
    exemplar_focus: list[str] = Field(default_factory=list, max_length=3)
    comparison_prompts: list[str] = Field(default_factory=list, max_length=4)
    observation_prompts: list[str] = Field(default_factory=list, max_length=4)
    response_prompts: list[str] = Field(default_factory=list, max_length=3)
    practice_hooks: list[str] = Field(default_factory=list, max_length=3)
    takeaways: list[str] = Field(min_length=2, max_length=6)
    next_steps: list[str] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def ensure_grounded_and_self_contained(self) -> 'LessonPlan':
        roles = [section.role for section in self.sections]
        section_blob = _pedagogy_blob([section.heading for section in self.sections] + [section.content for section in self.sections])
        opening_blob = _pedagogy_blob([section.content for section in self.sections[:2]])
        prompt_blob = _pedagogy_blob(self.observation_prompts + self.comparison_prompts + self.response_prompts + self.practice_hooks)
        headings = [section.heading.strip().lower() for section in self.sections]

        if len(set(headings)) < len(headings):
            raise ValueError('lesson sections should not reuse the same heading or loop through the same move twice.')
        if roles[0] not in {'core_concept', 'context', 'example'}:
            raise ValueError('lesson should open with the concept, context, or a concrete example.')
        if 'example' not in roles:
            raise ValueError('lesson must include at least one explicit example section.')
        if 'analysis' not in roles:
            raise ValueError('lesson must include an explanation or analysis section.')
        if self.comparison_prompts and 'comparison' not in roles:
            raise ValueError('lesson comparison prompts require a comparison section in the lesson body.')
        if (self.response_prompts or self.practice_hooks) and 'transfer' not in roles:
            raise ValueError('lesson must include a worked transfer section before practice or response prompts.')
        if 'transfer' in roles:
            transfer_index = roles.index('transfer')
            if 'example' in roles and roles.index('example') > transfer_index:
                raise ValueError('lesson must teach through the example before moving into transfer.')
            if 'analysis' in roles and roles.index('analysis') > transfer_index:
                raise ValueError('lesson must explain the example before moving into transfer.')

        if not _has_pedagogy_evidence(section_blob):
            raise ValueError('lesson must ground claims with concrete examples, cases, or evidence.')
        if not _contains_hint(section_blob, _PEDAGOGY_REASONING_HINTS):
            raise ValueError('lesson must explain why the evidence matters, not just name it.')
        if self.exemplar_focus and not _has_pedagogy_evidence(section_blob):
            raise ValueError('lesson exemplar must be operationalized through explanation or evidence.')
        if (self.response_prompts or self.practice_hooks) and (
            len(opening_blob) < 220 or not _has_pedagogy_evidence(opening_blob)
        ):
            raise ValueError('lesson must provide grounding before moving into response or practice.')
        if _contains_hint(section_blob, _ASSUMED_FAMILIARITY_HINTS):
            raise ValueError('lesson should not assume outside familiarity with the topic or source.')
        if prompt_blob and not _has_pedagogy_evidence(section_blob):
            raise ValueError('lesson scaffolding needs concrete teaching content behind it.')
        return self


class DeepLessonSection(BaseModel):
    role: Literal['core_concept', 'context', 'example', 'analysis', 'comparison', 'transfer']
    heading: str = Field(min_length=3, max_length=160)
    content: str = Field(min_length=80, max_length=1800)


class DeepLessonPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    summary: str = Field(min_length=30, max_length=420)
    essential_questions: list[str] = Field(min_length=2, max_length=6)
    sections: list[DeepLessonSection] = Field(min_length=3, max_length=8)
    exemplar_focus: list[str] = Field(default_factory=list, max_length=3)
    comparison_prompts: list[str] = Field(default_factory=list, max_length=4)
    observation_prompts: list[str] = Field(default_factory=list, max_length=5)
    response_prompts: list[str] = Field(default_factory=list, max_length=4)
    practice_hooks: list[str] = Field(default_factory=list, max_length=4)
    key_terms: list[LessonKeyConcept] = Field(min_length=3, max_length=10)
    study_prompts: list[str] = Field(min_length=2, max_length=6)

    @model_validator(mode='after')
    def ensure_deep_lesson_is_grounded(self) -> 'DeepLessonPlan':
        roles = [section.role for section in self.sections]
        section_blob = _pedagogy_blob([section.heading for section in self.sections] + [section.content for section in self.sections])
        opening_blob = _pedagogy_blob([section.content for section in self.sections[:2]])
        headings = [section.heading.strip().lower() for section in self.sections]

        if len(set(headings)) < len(headings):
            raise ValueError('deep lesson sections should remain distinct rather than repeating the same move.')
        if roles[0] not in {'core_concept', 'context', 'example'}:
            raise ValueError('deep lesson should open with a concrete anchor, concept, or minimal context.')
        if 'example' not in roles:
            raise ValueError('deep lesson must include an anchor example or close-reading section.')
        if 'analysis' not in roles:
            raise ValueError('deep lesson must include a real analysis section.')
        if 'comparison' not in roles:
            raise ValueError('deep lesson must include a comparison section.')
        if 'transfer' not in roles:
            raise ValueError('deep lesson must include a transfer or response section.')
        transfer_index = roles.index('transfer')
        if 'example' in roles and roles.index('example') > transfer_index:
            raise ValueError('deep lesson must teach through the anchor example before transfer.')
        if 'analysis' in roles and roles.index('analysis') > transfer_index:
            raise ValueError('deep lesson must analyze before transfer.')
        if 'comparison' in roles and roles.index('comparison') > transfer_index:
            raise ValueError('deep lesson must compare before transfer.')

        if _contains_hint(section_blob, _ASSUMED_FAMILIARITY_HINTS):
            raise ValueError('deep lesson should not depend on assumed prior familiarity.')
        if not _has_pedagogy_evidence(section_blob):
            raise ValueError('deep lesson must teach through concrete evidence, examples, or source-grounded detail.')
        if not _contains_hint(section_blob, _PEDAGOGY_REASONING_HINTS):
            raise ValueError('deep lesson must explain mechanisms, arguments, or consequences in detail.')
        if not _contains_hint(section_blob, _PEDAGOGY_COMPARISON_HINTS):
            raise ValueError('deep lesson should include at least one meaningful comparison or contrast.')
        if (self.response_prompts or self.practice_hooks or self.study_prompts) and (
            len(opening_blob) < 260 or not _has_pedagogy_evidence(opening_blob)
        ):
            raise ValueError('deep lesson must ground the learner before transfer or response prompts.')
        return self


class ExamplePlanItem(BaseModel):
    role: Literal['anchor', 'contrast', 'variation', 'transfer']
    name: str = Field(min_length=3, max_length=120)
    explanation: str = Field(min_length=60, max_length=500)
    why_it_matters: str = Field(min_length=30, max_length=280)

    @field_validator('name', mode='before')
    @classmethod
    def reject_generic_example_labels(cls, value: object) -> str:
        cleaned = ' '.join(str(value or '').split()).strip()
        if _GENERIC_EXAMPLE_NAME_PATTERN.match(cleaned):
            raise ValueError('example name must be specific, not a placeholder label.')
        return cleaned


class ExamplesPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    intro: str = Field(min_length=30, max_length=420)
    examples: list[ExamplePlanItem] = Field(min_length=3, max_length=6)
    exemplar_focus: list[str] = Field(default_factory=list, max_length=3)
    comparison_prompts: list[str] = Field(default_factory=list, max_length=4)
    observation_prompts: list[str] = Field(default_factory=list, max_length=4)
    response_prompts: list[str] = Field(default_factory=list, max_length=3)
    practice_hooks: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def ensure_examples_are_worked_and_transferable(self) -> 'ExamplesPlan':
        roles = [example.role for example in self.examples]
        intro_blob = _pedagogy_blob([self.intro])
        examples_blob = _pedagogy_blob(
            [example.role for example in self.examples]
            + [example.name for example in self.examples]
            + [example.explanation for example in self.examples]
            + [example.why_it_matters for example in self.examples]
        )
        prompt_blob = _pedagogy_blob(self.comparison_prompts + self.observation_prompts + self.response_prompts + self.practice_hooks)

        if roles[0] != 'anchor':
            raise ValueError('examples plan must start with an anchor example.')
        if 'transfer' not in roles:
            raise ValueError('examples plan must include a transfer example.')
        if not any(role in {'contrast', 'variation'} for role in roles[1:]):
            raise ValueError('examples plan must include a contrast or variation example after the anchor.')
        if roles.index('transfer') <= 0:
            raise ValueError('examples plan must move into transfer only after the anchor example.')
        if not _has_pedagogy_evidence(examples_blob):
            raise ValueError('examples plan must teach through concrete cases, evidence, or worked details.')
        if not _contains_hint(examples_blob, _PEDAGOGY_REASONING_HINTS):
            raise ValueError('examples plan must explain why each case matters, not just list it.')
        if not _contains_hint(f'{examples_blob} {prompt_blob}', _PEDAGOGY_COMPARISON_HINTS):
            raise ValueError('examples plan should include a comparison, contrast, or variation.')
        if (self.response_prompts or self.practice_hooks) and not _has_pedagogy_evidence(examples_blob):
            raise ValueError('examples plan must provide worked grounding before practice or response prompts.')
        if _contains_hint(f'{intro_blob} {examples_blob}', _ASSUMED_FAMILIARITY_HINTS):
            raise ValueError('examples plan should not rely on assumed outside familiarity.')
        return self


class ExercisePlanItem(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    task: str = Field(min_length=20, max_length=500)
    hints: list[str] = Field(min_length=1, max_length=4)
    expected_outcome: str = Field(min_length=15, max_length=300)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'


class ExercisesPlan(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    intro: str = Field(min_length=20, max_length=420)
    exercises: list[ExercisePlanItem] = Field(min_length=2, max_length=2)


class TutorReplyPlan(BaseModel):
    overview: str = Field(min_length=20, max_length=500)
    key_points: list[str] = Field(min_length=2, max_length=6)
    practical_steps: list[str] = Field(min_length=2, max_length=6)
    pitfalls: list[str] = Field(default_factory=list, max_length=4)
    next_step: str = Field(min_length=10, max_length=240)


class TopicRelevancePlan(BaseModel):
    relevance: Literal['relevant', 'related', 'unrelated']
    rationale: str = Field(min_length=10, max_length=280)


class TopicPlausibilityPlan(BaseModel):
    status: Literal['pass', 'clarify', 'needs_context', 'block']
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=12, max_length=320)
    suggested_reframe: str = Field(min_length=12, max_length=280)


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
