"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration for the SE layer. Values come from env / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- VLM (ingredient identification) ---
    llm_provider: Literal["anthropic", "openai", "gemini"] = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None

    # --- Nutrition ---
    nutrition_provider: Literal["usda"] = "usda"
    usda_api_key: SecretStr | None = None

    # --- PostgreSQL (aligned with docker-compose.yml `db` service) ---
    postgres_user: str = "postgres"
    postgres_password: str = "dev"
    postgres_db: str = "foodanalyzer"
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    database_url: str | None = None

    # --- SE layer ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    nutrition_cache_ttl_seconds: int = Field(default=86400, ge=0)
    max_image_size_mb: int = Field(default=5, ge=1)
    http_port: int = Field(default=8000, ge=1, le=65535)
    max_parallel: int = Field(default=10, ge=1)
    upload_dir: str = "uploads"

    @model_validator(mode="after")
    def build_database_url(self) -> Self:
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (reload in tests via get_settings.cache_clear())."""
    return Settings()
