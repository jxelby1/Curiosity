from __future__ import annotations

from sqlalchemy import text

from app.db import models  # noqa: F401
from app.db.database import Base, engine


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    statements = [
        "ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS progress_state VARCHAR(40) DEFAULT 'not_started'",
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS lesson_completed_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS examples_generated_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS exercises_completed_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS quiz_taken_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS best_quiz_score DOUBLE PRECISION DEFAULT 0',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS user_id INTEGER NULL',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS content_json JSON NULL',
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1',
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE',
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
