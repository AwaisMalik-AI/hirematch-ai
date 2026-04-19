"""Application settings loaded from environment (no secrets in code)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "HireMatch AI"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: PostgresDsn = Field(
        ...,
        alias="DATABASE_URL",
        description="Async PostgreSQL URL, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )

    # Redis
    redis_url: RedisDsn = Field(
        ...,
        alias="REDIS_URL",
        description="Redis URL for Celery broker/backend and caching",
    )

    # Security
    secret_key: str = Field(..., alias="SECRET_KEY", min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # LLM (OpenAI-compatible)
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="LLM_BASE_URL",
    )
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_timeout_seconds: float = 120.0

    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=1536, alias="EMBEDDING_DIMENSIONS")

    # Celery
    celery_broker_url: str | None = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")

    # SMTP (optional — outreach "sent" flows)
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    # Storage
    resume_storage_dir: str = Field(default="./data/resumes", alias="RESUME_STORAGE_DIR")

    # Matching weights (tunable)
    match_weight_semantic: float = 0.35
    match_weight_skills: float = 0.35
    match_weight_experience: float = 0.20
    match_weight_education: float = 0.10

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def celery_defaults_from_redis(self):
        r = str(self.redis_url)
        if self.celery_broker_url is None:
            object.__setattr__(self, "celery_broker_url", r)
        if self.celery_result_backend is None:
            object.__setattr__(self, "celery_result_backend", r)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
