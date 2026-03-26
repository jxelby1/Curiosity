from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '../.env'),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'Knowledge Base API'
    api_prefix: str = '/api'
    environment: str = 'development'

    database_url: str = Field(default='postgresql+psycopg://kb:kb@localhost:5432/knowledge_base')
    cors_origins: str = 'http://localhost:3000,http://127.0.0.1:3000'

    default_user_email: str = 'demo@knowledge-base.local'

    openai_api_key: str = Field(default='')
    openai_model: str = 'gpt-4.1-mini'
    openai_embedding_model: str = 'text-embedding-3-small'
    openai_timeout_seconds: float = 60.0

    jwt_secret_key: str = Field(default='change-me-in-production')
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = 60 * 24
    password_reset_token_ttl_minutes: int = 30
    password_reset_base_url: str = 'http://localhost:3000/reset-password'
    password_reset_debug_expose_token: bool = True
    password_reset_allow_user_discovery: bool = False
    password_reset_send_email: bool = False
    password_reset_email_subject: str = 'Reset your Knowledge Base password'

    email_provider: Literal['resend'] = 'resend'
    resend_api_key: str = Field(default='')
    resend_base_url: str = 'https://api.resend.com'
    resend_from_email: str = Field(default='')
    resend_reply_to: str = Field(default='')

    embedding_dimensions: int = 1536
    retrieval_top_k: int = 5
    max_note_chunk_chars: int = 900

    search_provider: Literal['serper'] = 'serper'
    search_api_key: str = Field(default='')
    search_base_url: str = 'https://google.serper.dev/search'

    enable_dev_unlocks: bool = True
    dev_unlock_emails: str = ''

    log_level: str = 'INFO'

    @model_validator(mode='after')
    def normalize_database_url(self) -> 'Settings':
        if self.database_url.startswith('postgres://'):
            self.database_url = self.database_url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif self.database_url.startswith('postgresql://'):
            self.database_url = self.database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(',') if item.strip()]

    @property
    def dev_unlock_email_list(self) -> list[str]:
        return [item.strip().lower() for item in self.dev_unlock_emails.split(',') if item.strip()]

    def validate_runtime_requirements(self) -> None:
        errors: list[str] = []

        if not self.database_url.startswith('postgresql+psycopg://'):
            errors.append(
                'DATABASE_URL must use PostgreSQL with psycopg driver, for example '
                'postgresql+psycopg://kb:kb@localhost:5432/knowledge_base'
            )

        if not self.openai_api_key:
            errors.append('OPENAI_API_KEY is required for live LLM and embeddings.')
        if self.jwt_secret_key == 'change-me-in-production' and self.environment.lower() == 'production':
            errors.append('JWT_SECRET_KEY must be set to a strong secret in production.')
        if self.password_reset_send_email and self.email_provider == 'resend':
            if not self.resend_api_key:
                errors.append('RESEND_API_KEY is required when PASSWORD_RESET_SEND_EMAIL=true.')
            if not self.resend_from_email:
                errors.append('RESEND_FROM_EMAIL is required when PASSWORD_RESET_SEND_EMAIL=true.')

        if errors:
            joined = '; '.join(errors)
            raise RuntimeError(f'Invalid runtime configuration: {joined}')


@lru_cache
def get_settings() -> Settings:
    return Settings()
