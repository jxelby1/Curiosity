from __future__ import annotations

from app.core.config import Settings


def test_openai_web_search_model_has_default() -> None:
    settings = Settings(
        _env_file=None,
        database_url='postgresql+psycopg://kb:kb@localhost:5432/knowledge_base',
        openai_api_key='test-key',
        jwt_secret_key='test-secret',
    )
    assert settings.openai_web_search_model
