from __future__ import annotations

from app.agents.assessment_agent import AssessmentAgent
from app.db.models import SkillNode, Topic


class _NoopLLM:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError('LLM should not be called in normalization test.')


def _topic_and_skill() -> tuple[Topic, SkillNode]:
    topic = Topic(id=1, user_id=1, name='Python basics', description='intro', goal='learn fundamentals')
    skill = SkillNode(
        id=2,
        topic_id=1,
        name='Variables and loops',
        description='Use variables and simple loops to solve beginner tasks.',
        difficulty=1,
        mastery_estimate=0.0,
    )
    return topic, skill


def test_normalization_realigns_non_reflection_questions_to_taught_concepts() -> None:
    topic, skill = _topic_and_skill()
    agent = AssessmentAgent(llm_service=_NoopLLM())  # type: ignore[arg-type]

    payload = {
        'title': 'Starter check',
        'instructions': 'Answer questions.',
        'difficulty': 1,
        'target_level': 'beginner',
        'questions': [
            {
                'id': 'q1',
                'assessment_style': 'short_answer',
                'question_type': 'short_answer',
                'prompt': 'Explain how recursion memoization works.',
                'expected_concepts': ['memoization', 'dynamic programming'],
                'difficulty': 1,
            },
            {
                'id': 'q2',
                'assessment_style': 'open_text',
                'question_type': 'reflection',
                'prompt': 'How did this node feel?',
                'difficulty': 1,
            },
            {
                'id': 'q3',
                'assessment_style': 'multiple_choice',
                'question_type': 'multiple_choice',
                'prompt': 'Which option best uses a loop?',
                'choices': ['A', 'B', 'C', 'D'],
                'answer_index': 0,
                'difficulty': 1,
            },
            {
                'id': 'q4',
                'assessment_style': 'scenario',
                'question_type': 'scenario',
                'prompt': 'Choose an approach for this loop scenario.',
                'expected_concepts': [],
                'difficulty': 1,
            },
        ],
    }

    normalized = agent._normalize_assessment_payload(  # type: ignore[attr-defined]
        payload,
        topic=topic,
        skill_node=skill,
        learner_level='beginner',
        question_count=4,
        style_sequence=['short_answer', 'open_text', 'multiple_choice', 'scenario'],
        taught_concepts=['Variables', 'Loops', 'Conditionals'],
    )

    non_reflection = [
        item
        for item in normalized['questions']
        if item['question_type'] != 'reflection'
    ]
    assert non_reflection
    for question in non_reflection:
        assert question['expected_concepts']
        assert any(
            concept.lower() in {'variables', 'loops', 'conditionals'}
            for concept in [str(item).lower() for item in question['expected_concepts']]
        )

