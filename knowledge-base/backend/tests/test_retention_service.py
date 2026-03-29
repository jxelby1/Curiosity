from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    MilestoneEvent,
    Recommendation,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    User,
    UserReminder,
    UserSkillState,
)
from app.services.retention import RetentionService


def _session() -> Session:
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    Recommendation.__table__.create(bind=engine)
    UserReminder.__table__.create(bind=engine)
    MilestoneEvent.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_retention_plan_generates_actionable_items_and_unlock_anticipation() -> None:
    db = _session()
    user = User(email='plan@test.local', hashed_password='x', display_name='Planner')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Python Debugging', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    node_a = SkillNode(topic_id=topic.id, name='Stack traces', description='desc', difficulty=1, mastery_estimate=0.2)
    node_b = SkillNode(topic_id=topic.id, name='Breakpoints', description='desc', difficulty=1, mastery_estimate=0.1)
    node_c = SkillNode(topic_id=topic.id, name='Postmortems', description='desc', difficulty=2, mastery_estimate=0.0)
    db.add_all([node_a, node_b, node_c])
    db.commit()
    db.refresh(node_a)
    db.refresh(node_b)
    db.refresh(node_c)

    db.add(SkillEdge(topic_id=topic.id, parent_skill_id=node_b.id, child_skill_id=node_c.id, edge_type='prerequisite'))
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=node_a.id,
            mastery=0.45,
            confidence=0.4,
            status=SkillStatus.in_progress,
            progress_state='learning',
            lesson_completed_at=datetime.utcnow(),
            exercises_completed_at=None,
            best_quiz_score=0.0,
            last_activity_at=datetime.utcnow(),
        )
    )
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=node_b.id,
            mastery=0.1,
            confidence=0.2,
            status=SkillStatus.available,
            progress_state='not_started',
            lesson_completed_at=None,
            exercises_completed_at=None,
            best_quiz_score=0.0,
            last_activity_at=datetime.utcnow(),
        )
    )
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=node_c.id,
            mastery=0.0,
            confidence=0.0,
            status=SkillStatus.locked,
            progress_state='not_started',
            lesson_completed_at=None,
            exercises_completed_at=None,
            best_quiz_score=0.0,
            last_activity_at=datetime.utcnow(),
        )
    )
    db.add(
        Recommendation(
            topic_id=topic.id,
            user_id=user.id,
            skill_node_id=node_b.id,
            rationale='Start this next.',
            action_type='study_generated',
            confidence=0.9,
        )
    )
    db.commit()

    service = RetentionService()
    payload = service.build_topic_loop(db, topic=topic, user_id=user.id, tree_stage=2)

    assert payload['cadence'] == 'daily'
    assert len(payload['next_actions']) >= 1
    assert payload['next_actions'][0].skill_node_id is not None
    assert payload['unlock_anticipation'] is not None
    assert payload['unlock_anticipation'].skill_node_id == node_c.id
    assert payload['unlock_anticipation'].steps


def test_inactivity_reminder_triggers_only_after_threshold() -> None:
    db = _session()
    user = User(email='reminder@test.local', hashed_password='x', display_name='Reminder')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='System Design', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    node = SkillNode(topic_id=topic.id, name='Basics', description='desc', difficulty=1, mastery_estimate=0.1)
    db.add(node)
    db.commit()
    db.refresh(node)

    stale_time = datetime.utcnow() - timedelta(days=4)
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=node.id,
            mastery=0.1,
            confidence=0.1,
            status=SkillStatus.available,
            progress_state='not_started',
            last_activity_at=stale_time,
        )
    )
    db.commit()

    service = RetentionService()
    stale_payload = service.build_topic_loop(db, topic=topic, user_id=user.id, tree_stage=1)
    assert stale_payload['reminder'] is not None

    state = db.scalar(
        select(UserSkillState).where(UserSkillState.user_id == user.id, UserSkillState.skill_node_id == node.id)
    )
    assert state is not None
    state.last_activity_at = datetime.utcnow()
    db.commit()

    fresh_payload = service.build_topic_loop(db, topic=topic, user_id=user.id, tree_stage=1)
    assert fresh_payload['reminder'] is None


def test_milestones_do_not_duplicate_on_repeated_generation() -> None:
    db = _session()
    user = User(email='milestone@test.local', hashed_password='x', display_name='Milestone')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Probability', description='d', goal='g')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    node = SkillNode(topic_id=topic.id, name='Core concepts', description='desc', difficulty=1, mastery_estimate=0.9)
    db.add(node)
    db.commit()
    db.refresh(node)

    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=node.id,
            mastery=0.9,
            confidence=0.9,
            status=SkillStatus.mastered,
            progress_state='verified',
            best_quiz_score=0.92,
            quiz_taken_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
        )
    )
    db.commit()

    service = RetentionService()
    service.build_topic_loop(db, topic=topic, user_id=user.id, tree_stage=6)
    first_count = db.scalar(select(func.count()).select_from(MilestoneEvent).where(MilestoneEvent.topic_id == topic.id))
    service.build_topic_loop(db, topic=topic, user_id=user.id, tree_stage=6)
    second_count = db.scalar(select(func.count()).select_from(MilestoneEvent).where(MilestoneEvent.topic_id == topic.id))
    assert first_count == second_count
