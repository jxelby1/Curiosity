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
        "ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS node_kind VARCHAR(40) DEFAULT 'core'",
        'ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS branch_parent_skill_id INTEGER NULL',
        'ALTER TABLE documents ADD COLUMN IF NOT EXISTS note_id INTEGER NULL',
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
        "ALTER TABLE notes ADD COLUMN IF NOT EXISTS tags JSON DEFAULT '[]'::json",
        "ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_type VARCHAR(60) DEFAULT 'user_authored'",
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_chat_session_id INTEGER NULL',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_message_id INTEGER NULL',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS created_from_skill_node_id INTEGER NULL',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS created_from_topic_id INTEGER NULL',
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
