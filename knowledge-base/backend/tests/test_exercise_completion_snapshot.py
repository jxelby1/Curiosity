from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import _exercise_completion_snapshot
from app.db.models import ExerciseCompletion, LearningResource, ResourceType, SkillNode, Topic, User


def _session():
    engine = create_engine('sqlite:///:memory:')
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    LearningResource.__table__.create(bind=engine)
    ExerciseCompletion.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_exercise_completion_snapshot_reports_individual_progress() -> None:
    db = _session()
    user = User(email='exercise-progress@test.local', hashed_password='x', display_name='Exercise User')
    db.add(user)
    db.commit()
    db.refresh(user)

    topic = Topic(user_id=user.id, name='Topic', description='desc', goal='goal')
    db.add(topic)
    db.commit()
    db.refresh(topic)

    skill = SkillNode(topic_id=topic.id, name='Skill', description='desc', difficulty=1, mastery_estimate=0.0)
    db.add(skill)
    db.commit()
    db.refresh(skill)

    resource = LearningResource(
        user_id=user.id,
        topic_id=topic.id,
        skill_node_id=skill.id,
        resource_type=ResourceType.generated_exercises,
        version=1,
        is_active=True,
        title='Exercises',
        summary='',
        content_json={
            'title': 'Exercises',
            'intro': 'intro',
            'exercises': [
                {'title': 'Exercise A', 'task': 'Do A', 'hints': ['h1'], 'expected_outcome': 'o1', 'difficulty': 'easy'},
                {'title': 'Exercise B', 'task': 'Do B', 'hints': ['h2'], 'expected_outcome': 'o2', 'difficulty': 'medium'},
            ],
        },
        content='',
        url='',
        relevance_reason='',
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    completion = ExerciseCompletion(
        user_id=user.id,
        topic_id=topic.id,
        skill_node_id=skill.id,
        resource_id=resource.id,
        exercise_index=0,
        exercise_title='Exercise A',
        completed_at=datetime.utcnow(),
        proof_filename='proof.png',
        proof_content_type='image/png',
        proof_storage_path='/tmp/fake-proof.png',
        proof_size_bytes=1234,
    )
    db.add(completion)
    db.commit()

    snapshot = _exercise_completion_snapshot(
        db,
        user_id=user.id,
        skill=skill,
    )
    assert snapshot.skill_node_id == skill.id
    assert snapshot.total_exercises == 2
    assert snapshot.completed_count == 1
    assert 0.49 <= snapshot.completion_ratio <= 0.51
    assert len(snapshot.completions) == 1
    assert snapshot.completions[0].exercise_index == 0
    assert snapshot.completions[0].proof_url == f'/api/exercise-completions/{completion.id}/proof'
