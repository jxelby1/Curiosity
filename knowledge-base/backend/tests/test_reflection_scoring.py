from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.assessment_agent import AssessmentAgent
from app.db.models import (
    Assessment,
    AssessmentFeedback,
    AssessmentQuestion,
    AssessmentQuestionType,
    AssessmentResponse,
    AssessmentAttempt,
    SkillNode,
    Topic,
    User,
)


class _LLMStub:
    async def generate_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError('LLM evaluation should not be called for this test case.')


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentQuestion.__table__.create(bind=engine)
    AssessmentAttempt.__table__.create(bind=engine)
    AssessmentResponse.__table__.create(bind=engine)
    AssessmentFeedback.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_reflection_questions_are_recorded_but_not_graded() -> None:
    db = _session()
    user = User(email='reflect@test.local', hashed_password='x', display_name='Reflect User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Python', description='desc', goal='goal')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Debug basics', description='skill', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    assessment = Assessment(
        topic_id=topic.id,
        skill_node_id=skill.id,
        user_id=user.id,
        title='Test assessment',
        questions=[],
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    mcq = AssessmentQuestion(
        assessment_id=assessment.id,
        assessment_style='multiple_choice',
        question_type=AssessmentQuestionType.multiple_choice,
        prompt='Choose the best answer',
        choices=['A', 'B', 'C', 'D'],
        expected_concepts=['concept'],
        rubric={'answer_index': 0},
        difficulty=1,
        order_index=0,
    )
    reflection = AssessmentQuestion(
        assessment_id=assessment.id,
        assessment_style='open_text',
        question_type=AssessmentQuestionType.reflection,
        prompt='What felt hardest?',
        choices=None,
        expected_concepts=[],
        rubric={},
        difficulty=1,
        order_index=1,
    )
    db.add(mcq)
    db.add(reflection)
    db.commit()

    agent = AssessmentAgent(llm_service=_LLMStub())  # type: ignore[arg-type]
    result = asyncio.run(
        agent.score_assessment(
            db,
            assessment=assessment,
            topic=topic,
            skill_node=skill,
            user_id=user.id,
            responses=[
                {'question_id': mcq.id, 'selected_option_index': 0},
                {'question_id': reflection.id, 'answer_text': 'I need to practice reading stack traces.'},
            ],
        )
    )

    assert result.overall_score == 1.0
    reflection_feedback = next(item for item in result.feedback if item['question_type'] == 'reflection')
    assert reflection_feedback['score'] is None
    assert 'Recorded' in reflection_feedback['feedback']
