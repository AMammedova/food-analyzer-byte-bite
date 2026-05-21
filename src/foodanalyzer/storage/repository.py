"""PostgreSQL repository for the `analyses` history table.

What this module does
---------------------
Persists one `AnalysisRecord` per analyzed meal. Three operations:

- init_db(conn)              — create the `analyses` table if missing
- save(conn, record)         — insert a record, return it with id + created_at
- list_recent(conn, limit)   — return the N most recent records, newest first

Why it lives in storage/ (not services/)
----------------------------------------
The services/ layer wraps external systems where retries and timeouts
matter (VLM, USDA). The DB is local infrastructure with its own pool —
different failure model, different concerns, so it gets its own package.

Design decisions
----------------
- Functions (not a class) take an explicit `conn`. The caller owns the
  connection lifecycle (acquired from `asyncpg.Pool`), so a request can
  do `init_db → save` in one transaction if it wants.

- ingredients/totals are stored as JSONB. We serialize them ourselves
  with `json.dumps` instead of registering an asyncpg codec, because:
    (a) it keeps the connection codec-free, so any pool works,
    (b) tests can mock `conn.fetch*` without setting up codecs.

- INSERT uses `RETURNING id, created_at` so we get the DB-assigned values
  in one round trip instead of a separate SELECT.

- `created_at` is set by `DEFAULT NOW()` server-side rather than by Python,
  so clock skew between app instances doesn't reorder history.

- `list_recent` orders by (created_at DESC, id DESC) — the id tiebreak
  makes ordering deterministic when two inserts share a timestamp.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from foodanalyzer.models import AnalysisRecord, IngredientOut, TotalsOut

logger = logging.getLogger(__name__)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS analyses (
    id          BIGSERIAL    PRIMARY KEY,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    image_path  TEXT         NOT NULL,
    ingredients JSONB        NOT NULL DEFAULT '[]'::jsonb,
    totals      JSONB        NOT NULL DEFAULT '{}'::jsonb
)
"""

_INSERT_SQL = """
INSERT INTO analyses (image_path, ingredients, totals)
VALUES ($1, $2::jsonb, $3::jsonb)
RETURNING id, created_at
"""

_LIST_RECENT_SQL = """
SELECT id, created_at, image_path, ingredients, totals
FROM analyses
ORDER BY created_at DESC, id DESC
LIMIT $1
"""


async def init_db(conn: Any) -> None:
    """Create the `analyses` table if it doesn't exist yet."""
    await conn.execute(_CREATE_TABLE_SQL)
    logger.info("analyses_table_ready")


async def save(conn: Any, record: AnalysisRecord) -> AnalysisRecord:
    """Insert a record and return it populated with id and created_at.

    Parameters
    ----------
    conn:
        An asyncpg connection (or pool) supporting `fetchrow`.
    record:
        The analysis to persist. Its `id` and `created_at` are ignored —
        the DB assigns both.

    Returns
    -------
    AnalysisRecord
        A copy of the input with `id` and `created_at` filled in.
    """
    ingredients_json = json.dumps(
        [ingredient.model_dump() for ingredient in record.ingredients]
    )
    totals_json = record.totals.model_dump_json()

    row = await conn.fetchrow(
        _INSERT_SQL,
        record.image_path,
        ingredients_json,
        totals_json,
    )

    logger.info(
        "analysis_saved",
        extra={
            "analysis_id": row["id"],
            "image_path": record.image_path,
            "ingredient_count": len(record.ingredients),
        },
    )

    return record.model_copy(
        update={"id": row["id"], "created_at": row["created_at"]}
    )


async def list_recent(conn: Any, limit: int = 20) -> list[AnalysisRecord]:
    """Return the `limit` most recent analyses, newest first.

    A non-positive `limit` returns an empty list without hitting the DB,
    so callers don't need to special-case zero before querying.
    """
    if limit <= 0:
        return []

    rows = await conn.fetch(_LIST_RECENT_SQL, limit)
    return [_row_to_record(row) for row in rows]


def _row_to_record(row: Any) -> AnalysisRecord:
    """Build an AnalysisRecord from an asyncpg row.

    Without a registered JSONB codec, asyncpg returns JSONB columns as
    `str`. We accept either: pre-decoded list/dict (codec present) or raw
    string (no codec), so this function works in both setups.
    """
    ingredients_raw = row["ingredients"]
    totals_raw = row["totals"]

    ingredients_data = (
        json.loads(ingredients_raw)
        if isinstance(ingredients_raw, str)
        else (ingredients_raw or [])
    )
    totals_data = (
        json.loads(totals_raw)
        if isinstance(totals_raw, str)
        else (totals_raw or {})
    )

    return AnalysisRecord(
        id=row["id"],
        created_at=row["created_at"],
        image_path=row["image_path"],
        ingredients=[IngredientOut(**item) for item in ingredients_data],
        totals=TotalsOut(**totals_data),
    )
