from __future__ import annotations

import asyncio

from app.agents.assessment_agent import AssessmentAgent
from app.core.exceptions import ProviderError
from app.db.models import SkillNode, Topic


class RepairingLLMStub:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, *, schema_model, repair_payload=None, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        payload = {
            'title': 'Starter assessment',
            'instructions': 'Answer all questions.',
            'difficulty': 1,
            'target_level': 'beginner',
            'questions': [
                {
                    'id': 'q1',
                    'assessment_style': 'multiple_choice',
                    'question_type': 'multiple_choice',
                    'prompt': 'Which option is best?',
                    'choices': ['A', 'B', 'C', 'D'],
                    'answer_index': 0,
                    'difficulty': 1,
                },
                {
                    'id': 'q2',
                    'assessment_style': 'short_answer',
                    'question_type': 'short_answer',
                    'prompt': 'Explain the core concept in one sentence.',
                    'expected_concepts': [],
                    'rubric': [],
                    'difficulty': 1,
                },
                {
                    'id': 'q3',
                    'assessment_style': 'scenario',
                    'question_type': 'scenario',
                    'prompt': 'What would you do first in a basic scenario?',
                    'expected_concepts': [],
                    'difficulty': 1,
                },
                {
                    'id': 'q4',
                    'assessment_style': 'open_text',
                    'question_type': 'reflection',
                    'prompt': 'How confident are you?',
                    'difficulty': 1,
                },
            ],
        }
        if repair_payload is not None:
            payload = repair_payload(payload)
        return schema_model.model_validate(payload)


class FailingLLMStub:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        raise ProviderError('forced failure')


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(id=1, user_id=1, name='Python debugging', description='debugging basics', goal='get better')
    skill = SkillNode(
        id=10,
        topic_id=1,
        name='Debugging basics',
        description='Understand simple debugging loops and print tracing.',
        difficulty=1,
        mastery_estimate=0.0,
    )
    return topic, skill


def test_assessment_generation_repairs_missing_expected_concepts() -> None:
    topic, skill = _topic_and_skill()
    agent = AssessmentAgent(llm_service=RepairingLLMStub())  # type: ignore[arg-type]

    plan, used_fallback = asyncio.run(
        agent._generate_assessment_plan_with_fallback(  # type: ignore[attr-defined]
            topic=topic,
            skill_node=skill,
            learner_level='beginner',
            technical_depth='intermediate',
            user_state=None,
            difficulty_band='foundation',
            prerequisite_names=[],
            question_count=4,
            recommended_mix={'multiple_choice': 1, 'short_answer': 1, 'scenario': 1, 'reflection': 1},
            style_sequence=['multiple_choice', 'short_answer', 'scenario', 'open_text'],
            allowed_styles=['multiple_choice', 'short_answer', 'scenario', 'open_text'],
            taught_concepts=['Debugging basics', 'print tracing', 'simple bug isolation'],
            taught_context_text='- Debugging basics\n- print tracing\n- simple bug isolation',
        )
    )

    assert used_fallback is False
    assert len(plan.questions) == 4
    for question in plan.questions:
        if question.question_type == 'reflection':
            continue
        assert len(question.expected_concepts) >= 1


def test_assessment_generation_uses_deterministic_fallback_when_llm_fails() -> None:
    topic, skill = _topic_and_skill()
    agent = AssessmentAgent(llm_service=FailingLLMStub())  # type: ignore[arg-type]

    plan, used_fallback = asyncio.run(
        agent._generate_assessment_plan_with_fallback(  # type: ignore[attr-defined]
            topic=topic,
            skill_node=skill,
            learner_level='beginner',
            technical_depth='intermediate',
            user_state=None,
            difficulty_band='foundation',
            prerequisite_names=[],
            question_count=8,
            recommended_mix={'multiple_choice': 2, 'short_answer': 2, 'scenario': 2, 'reflection': 2},
            style_sequence=['multiple_choice', 'short_answer', 'scenario', 'open_text', 'debugging'],
            allowed_styles=['multiple_choice', 'short_answer', 'scenario', 'open_text', 'debugging'],
            taught_concepts=['Debugging basics', 'print tracing'],
            taught_context_text='- Debugging basics\n- print tracing',
        )
    )

    assert used_fallback is True
    assert len(plan.questions) == 5
    assert len({item.question_type for item in plan.questions}) >= 3
    assert all(
        item.question_type == 'reflection' or len(item.expected_concepts) >= 1
        for item in plan.questions
    )
