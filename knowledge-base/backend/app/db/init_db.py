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
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255) DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_state VARCHAR(80) DEFAULT 'new'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(80) DEFAULT 'free'",
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INTEGER DEFAULT 0',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 1',
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferences JSON DEFAULT '{}'::json",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_goal_summary TEXT DEFAULT ''",
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL',
        "ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS node_kind VARCHAR(40) DEFAULT 'core'",
        "ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS branch_origin VARCHAR(60) DEFAULT 'core'",
        "ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS branch_purpose VARCHAR(60) DEFAULT 'core_curriculum'",
        'ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS branch_depth INTEGER DEFAULT 0',
        'ALTER TABLE skill_nodes ADD COLUMN IF NOT EXISTS branch_parent_skill_id INTEGER NULL',
        "ALTER TABLE topics ADD COLUMN IF NOT EXISTS course_depth VARCHAR(30) DEFAULT 'standard'",
        "ALTER TABLE topics ADD COLUMN IF NOT EXISTS starting_skill_level VARCHAR(30) DEFAULT 'beginner'",
        "ALTER TABLE topics ADD COLUMN IF NOT EXISTS allowed_assessment_styles JSON DEFAULT '[\"short_answer\",\"multiple_choice\",\"flashcard\"]'::json",
        'ALTER TABLE documents ADD COLUMN IF NOT EXISTS note_id INTEGER NULL',
        "ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS progress_state VARCHAR(40) DEFAULT 'not_started'",
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS force_unlocked BOOLEAN DEFAULT FALSE',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS lesson_completed_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS examples_generated_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS exercises_completed_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS quiz_taken_at TIMESTAMP NULL',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS best_quiz_score DOUBLE PRECISION DEFAULT 0',
        'ALTER TABLE user_skill_states ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP NULL',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS user_id INTEGER NULL',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE',
        'ALTER TABLE learning_resources ADD COLUMN IF NOT EXISTS content_json JSON NULL',
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1',
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE',
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS difficulty INTEGER DEFAULT 1',
        "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS target_level VARCHAR(40) DEFAULT 'beginner'",
        "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS question_mix JSON DEFAULT '{}'::json",
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS answers_revealed BOOLEAN DEFAULT FALSE',
        'ALTER TABLE assessments ADD COLUMN IF NOT EXISTS answers_revealed_at TIMESTAMP NULL',
        "ALTER TABLE assessment_questions ADD COLUMN IF NOT EXISTS assessment_style VARCHAR(40) DEFAULT 'short_answer'",
        "ALTER TABLE assessment_questions ADD COLUMN IF NOT EXISTS model_answer TEXT DEFAULT ''",
        "ALTER TABLE assessment_questions ADD COLUMN IF NOT EXISTS hints JSON DEFAULT '[]'::json",
        'ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS confidence_avg DOUBLE PRECISION DEFAULT 0',
        'ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS mastery_delta DOUBLE PRECISION DEFAULT 0',
        'ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS mastery_eligible BOOLEAN DEFAULT TRUE',
        'ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS practice_mode BOOLEAN DEFAULT FALSE',
        "ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS strengths JSON DEFAULT '[]'::json",
        "ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS weaknesses JSON DEFAULT '[]'::json",
        "ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS review_next TEXT DEFAULT ''",
        "ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS recommended_follow_up TEXT DEFAULT ''",
        "ALTER TABLE notes ADD COLUMN IF NOT EXISTS tags JSON DEFAULT '[]'::json",
        "ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_type VARCHAR(60) DEFAULT 'user_authored'",
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_chat_session_id INTEGER NULL',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS source_message_id INTEGER NULL',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS created_from_skill_node_id INTEGER NULL',
        'ALTER TABLE notes ADD COLUMN IF NOT EXISTS created_from_topic_id INTEGER NULL',
        'ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS used_at TIMESTAMP NULL',
        'ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NULL',
        "ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT 'queued'",
        "ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS current_step VARCHAR(120) DEFAULT 'queued'",
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS progress DOUBLE PRECISION DEFAULT 0',
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS ready_for_entry BOOLEAN DEFAULT FALSE',
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS background_complete BOOLEAN DEFAULT FALSE',
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS first_ready_skill_id INTEGER NULL',
        "ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS status_messages JSON DEFAULT '[]'::json",
        "ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS error_text TEXT DEFAULT ''",
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP NULL',
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS ready_at TIMESTAMP NULL',
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP NULL',
        'ALTER TABLE topic_initialization_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL',
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(
            text(
                "ALTER TABLE topics ALTER COLUMN allowed_assessment_styles SET DEFAULT '[\"short_answer\",\"multiple_choice\",\"flashcard\"]'::json"
            )
        )
