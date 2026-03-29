from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.profile_agent import ProfileAgent
from app.db.models import SkillEdge, SkillNode, SkillStatus, Topic, User, UserSkillState


def _session() -> Session:
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_force_unlocked_state_stays_available_even_if_prereqs_unverified() -> None:
    db = _session()
    user = User(email='dev@test.local', hashed_password='x', display_name='Dev')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Dev Topic', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    parent = SkillNode(topic_id=topic.id, name='Parent', description='desc', difficulty=1, mastery_estimate=0.0)
    child = SkillNode(topic_id=topic.id, name='Child', description='desc', difficulty=2, mastery_estimate=0.0)
    db.add_all([parent, child])
    db.commit()
    db.refresh(parent)
    db.refresh(child)

    db.add(SkillEdge(topic_id=topic.id, parent_skill_id=parent.id, child_skill_id=child.id, edge_type='prerequisite'))
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=parent.id,
            mastery=0.1,
            confidence=0.1,
            status=SkillStatus.available,
            progress_state='not_started',
            last_activity_at=datetime.utcnow(),
        )
    )
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=child.id,
            mastery=0.0,
            confidence=0.0,
            status=SkillStatus.available,
            progress_state='not_started',
            force_unlocked=True,
            last_activity_at=datetime.utcnow(),
        )
    )
    db.commit()

    agent = ProfileAgent()
    agent.recompute_unlocks(db, user.id, topic.id)

    child_state = db.scalar(
        select(UserSkillState).where(UserSkillState.user_id == user.id, UserSkillState.skill_node_id == child.id)
    )
    assert child_state is not None
    assert child_state.force_unlocked is True
    assert child_state.status != SkillStatus.locked
