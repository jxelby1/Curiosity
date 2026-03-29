from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Assessment,
    AssessmentAttempt,
    BranchSuggestion,
    LearningResource,
    ResourceType,
    SkillEdge,
    SkillNode,
    SkillStatus,
    Topic,
    User,
    UserSkillState,
)
from app.services.course_memory import CourseMemoryService


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    SkillEdge.__table__.create(bind=engine)
    UserSkillState.__table__.create(bind=engine)
    LearningResource.__table__.create(bind=engine)
    Assessment.__table__.create(bind=engine)
    AssessmentAttempt.__table__.create(bind=engine)
    BranchSuggestion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_course_memory_snapshot_captures_taught_and_future_context() -> None:
    db = _session()
    user = User(email='memory@test.local', hashed_password='x', display_name='Memory User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Modern Chinese History', description='Core events', goal='Build historical fluency')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    n1 = SkillNode(
        topic_id=topic.id,
        name='Chinese Civil War Overview',
        description='Pre-1949 context',
        difficulty=1,
        instructional_role='foundational_concept',
        status=SkillStatus.available,
        mastery_estimate=0.0,
    )
    n2 = SkillNode(
        topic_id=topic.id,
        name='Founding of the People’s Republic',
        description='State formation and institutions',
        difficulty=2,
        instructional_role='conceptual_bridge',
        status=SkillStatus.locked,
        mastery_estimate=0.0,
    )
    db.add_all([n1, n2])
    db.commit()
    db.refresh(n1)
    db.refresh(n2)

    db.add(
        SkillEdge(
            topic_id=topic.id,
            parent_skill_id=n1.id,
            child_skill_id=n2.id,
            edge_type='prerequisite',
        )
    )
    db.add(
        UserSkillState(
            user_id=user.id,
            skill_node_id=n1.id,
            mastery=0.81,
            progress_state='verified',
            status=SkillStatus.available,
        )
    )
    db.add(
        LearningResource(
            user_id=user.id,
            topic_id=topic.id,
            skill_node_id=n1.id,
            resource_type=ResourceType.generated_lesson,
            title='Lesson',
            summary='',
            content='',
            content_json={
                'key_concepts': [{'term': 'civil war', 'description': 'Key conflict dynamics'}],
                'sections': [{'heading': 'Power transitions'}],
            },
        )
    )
    db.add(
        LearningResource(
            user_id=user.id,
            topic_id=topic.id,
            skill_node_id=n1.id,
            resource_type=ResourceType.generated_examples,
            title='Examples',
            summary='',
            content='',
            content_json={
                'examples': [{'name': 'Northeast campaign', 'explanation': 'Operational and political constraints.'}],
            },
        )
    )
    db.commit()

    service = CourseMemoryService()
    snapshot = service.build_snapshot(db, topic=topic, user_id=user.id, focus_skill_id=n1.id)

    assert any('Chinese Civil War Overview' in item for item in snapshot.taught_node_lines)
    assert any('civil war' in item.lower() for item in snapshot.taught_concepts)
    assert any('Northeast campaign' in item for item in snapshot.used_examples)
    assert any('Founding of the People' in item for item in snapshot.future_core_lines)
    assert n1.id in snapshot.completed_node_ids


def test_course_memory_persistence_updates_topic_blueprint_and_ledger() -> None:
    db = _session()
    user = User(email='memory-persist@test.local', hashed_password='x', display_name='Memory Persist')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Art History', description='Klimt context', goal='Improve understanding')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    service = CourseMemoryService()
    snapshot = service.build_snapshot(db, topic=topic, user_id=user.id)
    service.persist_snapshot(db, topic=topic, snapshot=snapshot, reason='test_snapshot')
    service.persist_editorial_spine(
        db,
        topic=topic,
        spine={'core_arc': [], 'optional_arc': []},
        reason='test_spine',
    )
    db.commit()
    db.refresh(topic)

    assert topic.curriculum_ledger.get('reason') == 'test_snapshot'
    assert topic.curriculum_blueprint.get('reason') == 'test_spine'
