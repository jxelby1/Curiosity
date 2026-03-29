from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import dev_complete_skill
from app.db.models import Recommendation, SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    Recommendation.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_dev_complete_requires_dev_enabled_account() -> None:
    db = _session()
    user = User(email='learner@test.local', hashed_password='x', display_name='Learner', subscription_tier='free')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Topic', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Node', description='desc', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    try:
        asyncio.run(dev_complete_skill(skill.id, current_user=user, db=db))
        assert False, 'Expected HTTPException for non-dev account'
    except HTTPException as exc:
        assert exc.status_code == 403


def test_dev_complete_marks_node_verified_and_updates_progress_state() -> None:
    db = _session()
    user = User(email='dev@test.local', hashed_password='x', display_name='Dev', subscription_tier='dev')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Topic', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Node', description='desc', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    with patch('app.api.routes.topic_bootstrap_service.prepare_unlocked_nodes') as prepare_unlocked_nodes, patch(
        'app.api.routes._ensure_topic_milestone_events'
    ):
        result = asyncio.run(dev_complete_skill(skill.id, current_user=user, db=db))

    state = db.scalar(
        select(UserSkillState).where(
            UserSkillState.user_id == user.id,
            UserSkillState.skill_node_id == skill.id,
        )
    )
    assert state is not None
    assert state.force_unlocked is True
    assert state.lesson_completed_at is not None
    assert state.exercises_completed_at is not None
    assert state.quiz_taken_at is not None
    assert state.progress_state == 'verified'
    assert state.status == SkillStatus.mastered
    assert state.mastery >= 0.9
    assert result.progress_state == 'verified'
    assert result.status == SkillStatus.mastered
    prepare_unlocked_nodes.assert_called()
