"""Application settings for the catalog agent and book workflows."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database-only workflows do not require model credentials."""

    database_url: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(DatabaseSettings):
    """Settings for workflows that also use OpenAI models."""

    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    eval_judge_model: str | None = None


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """Return database configuration without requiring an OpenAI key."""
    return DatabaseSettings()


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
