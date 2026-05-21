"""Tests for src/foodanalyzer/storage/repository.py.

All tests are offline — asyncpg connections are mocked via unittest.mock.
No real PostgreSQL required.

Coverage targets
----------------
- init_db:
    - issues CREATE TABLE IF NOT EXISTS
- save:
    - calls fetchrow with INSERT...RETURNING
    - populates id and created_at from the DB row
    - serializes ingredients/totals as JSON for JSONB columns
    - leaves the input record unchanged (returns a copy)
- list_recent:
    - returns rows ordered by recency
    - default limit is 20
    - non-positive limit short-circuits without hitting the DB
    - parses JSONB columns whether they come back as str or pre-decoded
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from foodanalyzer.models import AnalysisRecord, IngredientOut, TotalsOut
from foodanalyzer.storage import repository


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_record(image_path: str = "uploads/meal.png") -> AnalysisRecord:
    """Build an AnalysisRecord with realistic content for save() tests."""
    return AnalysisRecord(
        image_path=image_path,
        ingredients=[
            IngredientOut(
                name="white rice (cooked)",
                estimated_grams=200.0,
                confidence=0.9,
                kcal=260.0,
                protein_g=5.4,
                carbs_g=56.0,
                fat_g=0.6,
            ),
            IngredientOut(
                name="broccoli",
                estimated_grams=80.0,
                confidence=0.8,
                kcal=27.2,
                protein_g=2.2,
                carbs_g=5.6,
                fat_g=0.3,
            ),
        ],
        totals=TotalsOut(
            kcal=287.2, protein_g=7.6, carbs_g=61.6, fat_g=0.9
        ),
    )


def make_db_row(
    *,
    row_id: int = 1,
    created_at: datetime | None = None,
    image_path: str = "uploads/meal.png",
    ingredients: list | str | None = None,
    totals: dict | str | None = None,
) -> dict:
    """Build a dict that quacks like an asyncpg.Record for tests."""
    if created_at is None:
        created_at = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
    if ingredients is None:
        ingredients = []
    if totals is None:
        totals = {}
    return {
        "id": row_id,
        "created_at": created_at,
        "image_path": image_path,
        "ingredients": ingredients,
        "totals": totals,
    }


# ─────────────────────────────────────────────────────────────────────────────
# init_db
# ─────────────────────────────────────────────────────────────────────────────


class TestInitDb:

    async def test_executes_create_table(self):
        """init_db issues a CREATE TABLE statement against the connection."""
        conn = AsyncMock()
        await repository.init_db(conn)
        conn.execute.assert_awaited_once()
        (sql,), _ = conn.execute.call_args
        assert "CREATE TABLE IF NOT EXISTS analyses" in sql

    async def test_create_table_declares_required_columns(self):
        """The schema covers the five columns the model needs."""
        conn = AsyncMock()
        await repository.init_db(conn)
        (sql,), _ = conn.execute.call_args
        for column in ("id", "created_at", "image_path", "ingredients", "totals"):
            assert column in sql
        assert "JSONB" in sql

    async def test_returns_none(self):
        """init_db has no return value — it is a side-effect call."""
        conn = AsyncMock()
        result = await repository.init_db(conn)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# save
# ─────────────────────────────────────────────────────────────────────────────


class TestSave:

    async def test_inserts_and_returns_record_with_id(self):
        """save returns a record with the DB-assigned id and created_at."""
        conn = AsyncMock()
        created_at = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
        conn.fetchrow.return_value = {"id": 42, "created_at": created_at}

        record = make_record()
        result = await repository.save(conn, record)

        assert result.id == 42
        assert result.created_at == created_at
        assert result.image_path == record.image_path
        assert result.ingredients == record.ingredients
        assert result.totals == record.totals

    async def test_uses_insert_returning_query(self):
        """The INSERT query uses RETURNING so we only do one round trip."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "id": 1,
            "created_at": datetime.now(timezone.utc),
        }
        await repository.save(conn, make_record())

        sql = conn.fetchrow.call_args.args[0]
        assert "INSERT INTO analyses" in sql
        assert "RETURNING id, created_at" in sql

    async def test_serializes_ingredients_as_json_string(self):
        """ingredients are sent to JSONB as a JSON-encoded string."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "id": 1,
            "created_at": datetime.now(timezone.utc),
        }
        record = make_record()
        await repository.save(conn, record)

        _, image_path, ingredients_json, totals_json = conn.fetchrow.call_args.args
        assert image_path == record.image_path

        ingredients_decoded = json.loads(ingredients_json)
        assert len(ingredients_decoded) == 2
        assert ingredients_decoded[0]["name"] == "white rice (cooked)"

        totals_decoded = json.loads(totals_json)
        assert totals_decoded["kcal"] == record.totals.kcal

    async def test_does_not_mutate_input_record(self):
        """save returns a copy — the input record stays as the caller passed it."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "id": 99,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        record = make_record()
        await repository.save(conn, record)
        assert record.id is None
        assert record.created_at is None

    async def test_empty_ingredients_serializes_to_empty_list(self):
        """A record with no ingredients sends `[]` to the DB, not null."""
        conn = AsyncMock()
        conn.fetchrow.return_value = {
            "id": 1,
            "created_at": datetime.now(timezone.utc),
        }
        record = AnalysisRecord(image_path="uploads/empty.png")
        await repository.save(conn, record)

        ingredients_json = conn.fetchrow.call_args.args[2]
        assert json.loads(ingredients_json) == []


# ─────────────────────────────────────────────────────────────────────────────
# list_recent
# ─────────────────────────────────────────────────────────────────────────────


class TestListRecent:

    async def test_returns_records_in_order(self):
        """Rows come back in the order the DB returned them (newest first)."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            make_db_row(row_id=3, image_path="uploads/a.png"),
            make_db_row(row_id=2, image_path="uploads/b.png"),
            make_db_row(row_id=1, image_path="uploads/c.png"),
        ]
        result = await repository.list_recent(conn, limit=10)

        assert [r.id for r in result] == [3, 2, 1]
        assert [r.image_path for r in result] == [
            "uploads/a.png", "uploads/b.png", "uploads/c.png",
        ]

    async def test_default_limit_is_twenty(self):
        """Calling without an explicit limit passes 20 to the query."""
        conn = AsyncMock()
        conn.fetch.return_value = []
        await repository.list_recent(conn)

        _, limit_arg = conn.fetch.call_args.args
        assert limit_arg == 20

    async def test_custom_limit_passed_to_query(self):
        """Caller-supplied limit reaches the SQL parameters."""
        conn = AsyncMock()
        conn.fetch.return_value = []
        await repository.list_recent(conn, limit=5)
        assert conn.fetch.call_args.args[1] == 5

    async def test_query_orders_by_created_at_desc(self):
        """The query orders newest-first, with id as the tiebreaker."""
        conn = AsyncMock()
        conn.fetch.return_value = []
        await repository.list_recent(conn)
        sql = conn.fetch.call_args.args[0]
        assert "ORDER BY created_at DESC" in sql
        assert "LIMIT $1" in sql

    async def test_zero_limit_short_circuits(self):
        """limit=0 returns [] without hitting the DB."""
        conn = AsyncMock()
        result = await repository.list_recent(conn, limit=0)
        assert result == []
        conn.fetch.assert_not_awaited()

    async def test_negative_limit_short_circuits(self):
        """Negative limit returns [] without hitting the DB."""
        conn = AsyncMock()
        result = await repository.list_recent(conn, limit=-3)
        assert result == []
        conn.fetch.assert_not_awaited()

    async def test_empty_table_returns_empty_list(self):
        """No rows in the DB → empty list, no errors."""
        conn = AsyncMock()
        conn.fetch.return_value = []
        result = await repository.list_recent(conn)
        assert result == []

    async def test_parses_jsonb_returned_as_string(self):
        """Without a JSONB codec asyncpg returns str — we decode it."""
        conn = AsyncMock()
        ingredients_str = json.dumps([
            {
                "name": "broccoli",
                "estimated_grams": 80.0,
                "confidence": 0.8,
                "kcal": 27.2,
                "protein_g": 2.2,
                "carbs_g": 5.6,
                "fat_g": 0.3,
            }
        ])
        totals_str = json.dumps(
            {"kcal": 27.2, "protein_g": 2.2, "carbs_g": 5.6, "fat_g": 0.3}
        )
        conn.fetch.return_value = [
            make_db_row(ingredients=ingredients_str, totals=totals_str)
        ]
        result = await repository.list_recent(conn)

        assert len(result) == 1
        assert result[0].ingredients[0].name == "broccoli"
        assert result[0].totals.kcal == 27.2

    async def test_parses_jsonb_returned_pre_decoded(self):
        """With a JSONB codec asyncpg returns list/dict — we accept that too."""
        conn = AsyncMock()
        conn.fetch.return_value = [
            make_db_row(
                ingredients=[
                    {
                        "name": "broccoli",
                        "estimated_grams": 80.0,
                        "confidence": 0.8,
                        "kcal": 27.2,
                        "protein_g": 2.2,
                        "carbs_g": 5.6,
                        "fat_g": 0.3,
                    }
                ],
                totals={"kcal": 27.2, "protein_g": 2.2, "carbs_g": 5.6, "fat_g": 0.3},
            )
        ]
        result = await repository.list_recent(conn)

        assert len(result) == 1
        assert result[0].ingredients[0].name == "broccoli"
        assert result[0].totals.kcal == 27.2

    async def test_null_jsonb_columns_become_empty(self):
        """A row with NULL JSONB columns yields empty ingredients / default totals."""
        conn = AsyncMock()
        conn.fetch.return_value = [make_db_row(ingredients=None, totals=None)]
        result = await repository.list_recent(conn)
        assert result[0].ingredients == []
        assert result[0].totals == TotalsOut()
