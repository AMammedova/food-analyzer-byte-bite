"""Connection pool lifecycle for the PostgreSQL storage layer.

Why this module exists
----------------------
`repository.py` takes a `conn` (or pool — asyncpg's pool exposes the same
query methods). It does not own the connection lifecycle. The HTTP app
and the CLI both need a small, shared place that:

- builds an `asyncpg.Pool` from settings,
- runs `init_db` once on startup,
- closes the pool cleanly on shutdown.

This is exactly that. Keeping pool concerns separate from query logic
means repository tests can mock connections trivially, and pool tests
can mock `asyncpg.create_pool` without touching SQL.

DSN note
--------
`Settings.database_url` is built in SQLAlchemy form
(`postgresql+asyncpg://…`). asyncpg's `create_pool` does **not** accept
the `+asyncpg` driver suffix and will raise. We strip it here so that a
single env var works for both an eventual SQLAlchemy engine and the
asyncpg pool.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import asyncpg

from foodanalyzer.storage import repository

if TYPE_CHECKING:
    from foodanalyzer.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_MIN_POOL_SIZE = 1
DEFAULT_MAX_POOL_SIZE = 10


def _to_asyncpg_dsn(database_url: str) -> str:
    """Drop SQLAlchemy's `+asyncpg` driver suffix from a DSN."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_pool(
    settings: Settings | Any,
    *,
    min_size: int = DEFAULT_MIN_POOL_SIZE,
    max_size: int = DEFAULT_MAX_POOL_SIZE,
) -> asyncpg.Pool:
    """Open an asyncpg connection pool from project settings.

    Parameters
    ----------
    settings:
        Anything exposing a `database_url` attribute. In production this
        is the cached `Settings` instance from `foodanalyzer.config`; tests
        pass a `SimpleNamespace` to avoid importing the global settings.
    min_size, max_size:
        Lower/upper bounds for pool size. Defaults are sized for a single
        API instance handling tens of concurrent uploads — bump for higher
        concurrency, lower for tests/CLI scripts.
    """
    dsn = _to_asyncpg_dsn(settings.database_url)
    pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    logger.info(
        "db_pool_opened",
        extra={"min_size": min_size, "max_size": max_size},
    )
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    """Drain and close the pool. Safe to call on a fresh pool."""
    await pool.close()
    logger.info("db_pool_closed")


async def init_schema(pool: asyncpg.Pool) -> None:
    """Run `repository.init_db` once on a connection from the pool.

    Acquires a single connection, creates the `analyses` table if missing,
    and releases the connection back to the pool. Idempotent — safe to
    call on every app startup.
    """
    async with pool.acquire() as conn:
        await repository.init_db(conn)
    logger.info("db_schema_ready")
