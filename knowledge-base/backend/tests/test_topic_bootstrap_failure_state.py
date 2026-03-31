from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.topic_bootstrap as topic_bootstrap_module
from app.db.models import SkillNode, Topic, TopicInitializationJob, User
from app.services.topic_bootstrap import TopicBootstrapService


def _session_factory():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    Topic.__table__.create(bind=engine)
    SkillNode.__table__.create(bind=engine)
    TopicInitializationJob.__table__.create(bind=engine)
    return sessionmaker(bind=engine)


def _service() -> TopicBootstrapService:
    return TopicBootstrapService(
        skill_graph_agent=object(),  # type: ignore[arg-type]
        profile_agent=object(),  # type: ignore[arg-type]
        resource_agent=object(),  # type: ignore[arg-type]
        assessment_agent=object(),  # type: ignore[arg-type]
    )


def test_run_job_sets_failed_status_when_blocking_stage_raises(monkeypatch) -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        user = User(email='bootstrap-fail@test.local', hashed_password='x', display_name='Bootstrap Fail')
        db.add(user)
        db.commit()
        db.refresh(user)

        topic = Topic(user_id=user.id, name='Bootstrap topic', description='desc', goal='goal')
        db.add(topic)
        db.commit()
        db.refresh(topic)

        job = TopicInitializationJob(
            topic_id=topic.id,
            user_id=user.id,
            status='running',
            current_step='Preparing your first lesson',
            progress=0.46,
            status_messages=['Preparing your first lesson'],
            error_text='',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id

    monkeypatch.setattr(topic_bootstrap_module, 'SessionLocal', SessionLocal)

    service = _service()

    async def _raise_failure(job_id: int) -> int:  # noqa: ARG001
        raise RuntimeError('forced bootstrap failure')

    service._run_blocking_stage = _raise_failure  # type: ignore[assignment]

    asyncio.run(service._run_job(job_id))

    with SessionLocal() as db:
        updated = db.get(TopicInitializationJob, job_id)
        assert updated is not None
        assert updated.status == 'failed'
        assert updated.current_step == 'Setup failed'
        assert 'could not finish preparing your topic' in updated.error_text.lower()
        assert any('retry' in msg.lower() for msg in (updated.status_messages or []))
