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


def _core_node(topic_id: int, name: str, difficulty: int, status: SkillStatus) -> SkillNode:
    return SkillNode(
        topic_id=topic_id,
        node_kind='core',
        branch_origin='core',
        branch_purpose='core_curriculum',
        branch_depth=0,
        branch_parent_skill_id=None,
        name=name,
        description=f'{name} description',
        difficulty=difficulty,
        mastery_estimate=0.0,
        status=status,
    )


def test_recompute_unlocks_uses_normalized_core_prerequisites_for_orphan_repairs() -> None:
    db = _session()
    user = User(email='unlock-normalization@test.local', hashed_password='x', display_name='Unlock Normalization')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Core Repair Topic', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    root = _core_node(topic.id, 'Root', 1, SkillStatus.available)
    middle = _core_node(topic.id, 'Middle', 2, SkillStatus.locked)
    orphan_tail = _core_node(topic.id, 'Tail', 3, SkillStatus.available)
    db.add_all([root, middle, orphan_tail])
    db.commit()
    db.refresh(root)
    db.refresh(middle)
    db.refresh(orphan_tail)

    # Intentionally omit middle -> tail edge to mirror orphaned core tail regressions.
    db.add(SkillEdge(topic_id=topic.id, parent_skill_id=root.id, child_skill_id=middle.id, edge_type='prerequisite'))
    db.commit()

    db.add_all(
        [
            UserSkillState(
                user_id=user.id,
                skill_node_id=root.id,
                mastery=0.15,
                confidence=0.1,
                status=SkillStatus.available,
                progress_state='not_started',
                last_activity_at=datetime.utcnow(),
            ),
            UserSkillState(
                user_id=user.id,
                skill_node_id=middle.id,
                mastery=0.0,
                confidence=0.0,
                status=SkillStatus.locked,
                progress_state='not_started',
                last_activity_at=datetime.utcnow(),
            ),
            UserSkillState(
                user_id=user.id,
                skill_node_id=orphan_tail.id,
                mastery=0.0,
                confidence=0.0,
                status=SkillStatus.available,
                progress_state='not_started',
                last_activity_at=datetime.utcnow(),
            ),
        ]
    )
    db.commit()

    agent = ProfileAgent()
    agent.recompute_unlocks(db, user.id, topic.id)

    repaired_tail = db.scalar(
        select(UserSkillState).where(
            UserSkillState.user_id == user.id,
            UserSkillState.skill_node_id == orphan_tail.id,
        )
    )
    assert repaired_tail is not None
    assert repaired_tail.status == SkillStatus.locked


def test_generated_examples_do_not_unlock_node_with_unmet_prerequisites() -> None:
    db = _session()
    user = User(email='unlock-preload@test.local', hashed_password='x', display_name='Unlock Preload')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Preload Lock Topic', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    parent = _core_node(topic.id, 'Parent', 1, SkillStatus.available)
    child = _core_node(topic.id, 'Child', 2, SkillStatus.locked)
    db.add_all([parent, child])
    db.commit()
    db.refresh(parent)
    db.refresh(child)

    db.add(SkillEdge(topic_id=topic.id, parent_skill_id=parent.id, child_skill_id=child.id, edge_type='prerequisite'))
    db.commit()

    db.add_all(
        [
            UserSkillState(
                user_id=user.id,
                skill_node_id=parent.id,
                mastery=0.2,
                confidence=0.2,
                status=SkillStatus.available,
                progress_state='not_started',
                last_activity_at=datetime.utcnow(),
            ),
            UserSkillState(
                user_id=user.id,
                skill_node_id=child.id,
                mastery=0.0,
                confidence=0.0,
                status=SkillStatus.locked,
                progress_state='not_started',
                last_activity_at=datetime.utcnow(),
            ),
        ]
    )
    db.commit()

    agent = ProfileAgent()
    agent.record_generated_content(db, user.id, child, 'examples')

    child_state = db.scalar(
        select(UserSkillState).where(
            UserSkillState.user_id == user.id,
            UserSkillState.skill_node_id == child.id,
        )
    )
    assert child_state is not None
    assert child_state.examples_generated_at is not None
    assert child_state.status == SkillStatus.locked
