from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.assessment_agent import AssessmentAgent
from app.core.course_preferences import ASSESSMENT_STYLE_TO_QUESTION_TYPE
from app.db.models import Assessment, AssessmentQuestion, SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState


class _AssessmentLLMStub:
    async def generate_structured(self, *, schema_model, repair_payload=None, **kwargs):  # type: ignore[no-untyped-def]
        payload = {
            'title': 'Adaptive assessment',
            'instructions': 'Answer clearly.',
            'difficulty': 2,
            'target_level': 'intermediate',
            'questions': [],
        }
        if repair_payload is not None:
            payload = repair_payload(payload)
        return schema_model.model_validate(payload)


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentQuestion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _setup_topic_and_skill(
    db,
    *,
    topic_name: str,
    topic_description: str,
    allowed_styles: list[str],
) -> tuple[User, Topic, SkillNode]:
    user = User(email=f'{topic_name.replace(" ", "").lower()}@test.local', hashed_password='x', display_name='User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(
        user_id=user.id,
        name=topic_name,
        description=topic_description,
        goal='Improve skill',
        allowed_assessment_styles=allowed_styles,
        starting_skill_level='intermediate',
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(
        topic_id=topic.id,
        name='Core node',
        description='Node-specific details',
        difficulty=3,
        mastery_estimate=0.0,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)

    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=skill.id,
            mastery=0.45,
            confidence=0.4,
            status=SkillStatus.available,
            progress_state='learning',
        )
    )
    db.commit()
    return user, topic, skill


def test_assessment_generation_respects_allowed_styles_for_code_topic() -> None:
    db = _session()
    allowed_styles = ['multiple_choice', 'coding', 'debugging', 'code_completion', 'code_interpretation']
    user, topic, skill = _setup_topic_and_skill(
        db,
        topic_name='Python debugging',
        topic_description='Debug stack traces and inspect code paths',
        allowed_styles=allowed_styles,
    )

    agent = AssessmentAgent(llm_service=_AssessmentLLMStub())  # type: ignore[arg-type]
    assessment, _ = asyncio.run(
        agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill,
            user_id=user.id,
            question_count=6,
            regenerate=True,
            preferred_styles=None,
        )
    )

    styles = [item['assessment_style'] for item in assessment.questions]
    assert all(style in allowed_styles for style in styles)
    assert any(style in {'coding', 'debugging', 'code_completion', 'code_interpretation'} for style in styles)
    for item in assessment.questions:
        style = item['assessment_style']
        if item['question_type'] == 'reflection':
            continue
        assert item['question_type'] == ASSESSMENT_STYLE_TO_QUESTION_TYPE[style]


def test_assessment_generation_includes_math_style_when_topic_is_quantitative() -> None:
    db = _session()
    allowed_styles = ['math_problem', 'short_answer', 'multiple_choice', 'scenario']
    user, topic, skill = _setup_topic_and_skill(
        db,
        topic_name='Probability',
        topic_description='Quantitative reasoning and probability calculations',
        allowed_styles=allowed_styles,
    )

    agent = AssessmentAgent(llm_service=_AssessmentLLMStub())  # type: ignore[arg-type]
    assessment, _ = asyncio.run(
        agent.generate_assessment(
            db,
            topic=topic,
            skill_node=skill,
            user_id=user.id,
            question_count=6,
            regenerate=True,
            preferred_styles=None,
        )
    )

    styles = [item['assessment_style'] for item in assessment.questions]
    assert 'math_problem' in styles
    assert all(style in allowed_styles for style in styles)
