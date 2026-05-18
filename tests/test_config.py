"""Tests for application configuration (offline)."""

from __future__ import annotations

from foodanalyzer.config import Settings, get_settings


def test_settings_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.llm_provider == "anthropic"
    assert s.nutrition_provider == "usda"
    assert s.postgres_user == "postgres"
    assert s.postgres_db == "foodanalyzer"
    assert s.postgres_host == "localhost"
    assert s.postgres_port == 5432
    assert (
        s.database_url
        == "postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer"
    )
    assert s.nutrition_cache_ttl_seconds == 86400
    assert s.max_image_size_mb == 5
    assert s.max_image_size_bytes == 5 * 1024 * 1024
    assert s.max_parallel == 10
    assert s.http_port == 8000


def test_database_url_built_from_postgres_env(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "appuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_DB", "foodanalyzer")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert "appuser:secret@localhost:5433/foodanalyzer" in s.database_url


def test_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("HTTP_PORT", "9000")
    monkeypatch.setenv("MAX_PARALLEL", "5")
    get_settings.cache_clear()
    try:
        s = Settings()
        assert s.log_level == "DEBUG"
        assert s.http_port == 9000
        assert s.max_parallel == 5
    finally:
        get_settings.cache_clear()
