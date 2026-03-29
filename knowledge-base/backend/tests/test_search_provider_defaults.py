from __future__ import annotations

from app.core.config import Settings


def test_search_provider_defaults_to_openai_web() -> None:
    settings = Settings(
        _env_file=None,
        database_url='postgresql+psycopg://kb:kb@localhost:5432/knowledge_base',
        openai_api_key='test-key',
        jwt_secret_key='test-secret',
    )
    assert settings.search_provider == 'openai_web'
    assert settings.openai_web_search_model
