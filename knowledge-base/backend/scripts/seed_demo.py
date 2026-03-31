from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.agents.ingestion_agent import IngestionAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.skill_graph_agent import SkillGraphAgent
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import SkillNode, Topic, User
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService


async def run() -> None:
    settings = get_settings()
    settings.validate_runtime_requirements()
    init_db()

    llm_service = LLMService()
    embedding_service = EmbeddingService()

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.id == 1))
        if not user:
            user = User(
                id=1,
                email=settings.default_user_email,
                display_name='Demo User',
                hashed_password=hash_password('password123'),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.hashed_password:
            user.hashed_password = hash_password('password123')
            db.commit()

        topic = db.scalar(select(Topic).where(Topic.user_id == user.id, Topic.name == 'Python Debugging'))
        if not topic:
            topic = Topic(
                user_id=user.id,
                name='Python Debugging',
                description='Learn to diagnose and fix Python issues quickly.',
                goal='Reach intermediate debugging ability in 6 weeks.',
            )
            db.add(topic)
            db.commit()
            db.refresh(topic)

        existing_node = db.scalar(select(SkillNode).where(SkillNode.topic_id == topic.id))
        if not existing_node:
            await SkillGraphAgent(llm_service).create_skill_tree(db, topic)

        profile_agent = ProfileAgent()
        profile_agent.ensure_states_for_topic(db, user.id, topic.id)

        sample_note = (
            'Use traceback from bottom to top. Reproduce bugs with minimal scripts. '
            'Add logging around input assumptions. Use pdb breakpoints to inspect variable state. '
            'Test edge cases and type mismatches.'
        )

        ingestion_agent = IngestionAgent(embedding_service)
        await ingestion_agent.ingest_text(
            db,
            topic_id=topic.id,
            user_id=user.id,
            filename='debugging-notes.txt',
            content_type='text/plain',
            text=sample_note,
        )

        profile_agent.infer_mastery_from_notes(db, user.id, topic.id)

        print('Seeded demo data successfully.')
    finally:
        db.close()


if __name__ == '__main__':
    asyncio.run(run())
