"""Tests for src/foodanalyzer/storage/db.py — pool lifecycle helpers.

All tests are offline: asyncpg.create_pool is patched and the pool itself
is an AsyncMock. No real PostgreSQL required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from foodanalyzer.storage import db


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_settings(
    database_url: str = "postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer",
) -> SimpleNamespace:
    """Build a settings stand-in with just the attributes db.py needs."""
    return SimpleNamespace(database_url=database_url)


def make_pool_with_conn() -> tuple[MagicMock, AsyncMock]:
    """Build a fake pool whose `acquire()` yields a mock connection."""
    pool = MagicMock()
    conn = AsyncMock()

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    pool.close = AsyncMock()
    return pool, conn


# ─────────────────────────────────────────────────────────────────────────────
# _to_asyncpg_dsn
# ─────────────────────────────────────────────────────────────────────────────


class TestDsnNormalization:

    def test_strips_sqlalchemy_driver_suffix(self):
        """`postgresql+asyncpg://` → `postgresql://`."""
        url = "postgresql+asyncpg://u:p@h:5432/db"
        assert db._to_asyncpg_dsn(url) == "postgresql://u:p@h:5432/db"

    def test_passes_clean_url_through_unchanged(self):
        """A DSN without the suffix is returned unchanged."""
        url = "postgresql://u:p@h:5432/db"
        assert db._to_asyncpg_dsn(url) == url

    def test_only_replaces_scheme_prefix(self):
        """Suffix-like substrings later in the URL are not rewritten."""
        url = "postgresql+asyncpg://u:p@h:5432/db?app=postgresql+asyncpg"
        result = db._to_asyncpg_dsn(url)
        assert result.startswith("postgresql://")
        assert "app=postgresql+asyncpg" in result


# ─────────────────────────────────────────────────────────────────────────────
# create_pool
# ─────────────────────────────────────────────────────────────────────────────


class TestCreatePool:

    async def test_calls_asyncpg_with_clean_dsn(self):
        """create_pool passes the asyncpg-normalized DSN, not the SQLAlchemy one."""
        with patch("foodanalyzer.storage.db.asyncpg.create_pool", new=AsyncMock()) as cp:
            cp.return_value = MagicMock()
            await db.create_pool(make_settings())

        cp.assert_awaited_once()
        dsn = cp.call_args.args[0]
        assert dsn == "postgresql://postgres:dev@localhost:5432/foodanalyzer"
        assert "+asyncpg" not in dsn

    async def test_default_pool_sizes(self):
        """Defaults match DEFAULT_MIN_POOL_SIZE / DEFAULT_MAX_POOL_SIZE."""
        with patch("foodanalyzer.storage.db.asyncpg.create_pool", new=AsyncMock()) as cp:
            await db.create_pool(make_settings())

        kwargs = cp.call_args.kwargs
        assert kwargs["min_size"] == db.DEFAULT_MIN_POOL_SIZE
        assert kwargs["max_size"] == db.DEFAULT_MAX_POOL_SIZE

    async def test_custom_pool_sizes(self):
        """Caller can override min/max pool sizes."""
        with patch("foodanalyzer.storage.db.asyncpg.create_pool", new=AsyncMock()) as cp:
            await db.create_pool(make_settings(), min_size=3, max_size=20)

        kwargs = cp.call_args.kwargs
        assert kwargs["min_size"] == 3
        assert kwargs["max_size"] == 20

    async def test_returns_asyncpg_pool(self):
        """Whatever asyncpg.create_pool returns is what create_pool returns."""
        fake_pool = MagicMock()
        with patch(
            "foodanalyzer.storage.db.asyncpg.create_pool",
            new=AsyncMock(return_value=fake_pool),
        ):
            result = await db.create_pool(make_settings())
        assert result is fake_pool


# ─────────────────────────────────────────────────────────────────────────────
# close_pool
# ─────────────────────────────────────────────────────────────────────────────


class TestClosePool:

    async def test_awaits_pool_close(self):
        """close_pool delegates to the pool's async close()."""
        pool = MagicMock()
        pool.close = AsyncMock()
        await db.close_pool(pool)
        pool.close.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# init_schema
# ─────────────────────────────────────────────────────────────────────────────


class TestInitSchema:

    async def test_acquires_connection_and_runs_repository_init(self):
        """init_schema acquires a conn from the pool and runs repository.init_db."""
        pool, conn = make_pool_with_conn()

        with patch(
            "foodanalyzer.storage.db.repository.init_db", new=AsyncMock()
        ) as init_db_mock:
            await db.init_schema(pool)

        pool.acquire.assert_called_once()
        init_db_mock.assert_awaited_once_with(conn)

    async def test_releases_connection_even_on_init_failure(self):
        """A failing init_db still triggers the `async with` __aexit__."""
        pool, conn = make_pool_with_conn()

        with patch(
            "foodanalyzer.storage.db.repository.init_db",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with pytest.raises(RuntimeError):
                await db.init_schema(pool)

        pool.acquire.return_value.__aexit__.assert_awaited_once()
