"""Tests for src/foodanalyzer/api.py — POST /analyze, GET /health, GET /history.

All tests are offline — no real PostgreSQL, no VLM API, no network.

Isolation strategy
------------------
`create_app()` accepts a `lifespan_handler` so tests pass a no-op lifespan
that skips the real DB pool. The app.state.vlm / app.state.nutrition slots
are replaced with offline fakes. DB operations are injected via
`app.state.history_repo` — a lightweight in-memory stub that satisfies the
same interface as the real repository functions.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from foodanalyzer.api import create_app
from foodanalyzer.models import AnalysisRecord, IngredientOut, TotalsOut
from tests.conftest import FakeNutrition, FakeVLM


# ---------------------------------------------------------------------------
# Minimal PNG / JPEG bytes for upload tests
# ---------------------------------------------------------------------------

_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000"
    "00907753de0000000c4944415408d76360000000000004000146a13a"
    "020000000049454e44ae426082"
)
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20


# ---------------------------------------------------------------------------
# In-memory repository stub
# ---------------------------------------------------------------------------


class _InMemoryRepo:
    """Minimal in-memory stand-in for the real asyncpg-backed repository."""

    def __init__(self, records: list[AnalysisRecord] | None = None) -> None:
        self._records: list[AnalysisRecord] = list(records or [])
        self._next_id = 1

    async def save(self, record: AnalysisRecord) -> AnalysisRecord:
        saved = record.model_copy(
            update={
                "id": self._next_id,
                "created_at": datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
            }
        )
        self._records.insert(0, saved)
        self._next_id += 1
        return saved

    async def list_recent(
        self, limit: int = 20, offset: int = 0
    ) -> list[AnalysisRecord]:
        if limit <= 0:
            return []
        return self._records[offset : offset + limit]


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _no_op_lifespan(app):
    """Skip real DB pool — tests inject a repo stub via app.state."""
    yield


def _make_client(
    *,
    vlm: Any = None,
    nutrition: Any = None,
    repo: _InMemoryRepo | None = None,
) -> TestClient:
    """Build a synchronous TestClient with offline providers injected."""
    app = create_app(lifespan_handler=_no_op_lifespan)
    app.state.vlm = vlm or FakeVLM()
    app.state.nutrition = nutrition or FakeNutrition()
    app.state.history_repo = repo or _InMemoryRepo()
    return TestClient(app, raise_server_exceptions=True)


def _upload(client: TestClient, data: bytes, filename: str = "meal.png") -> Any:
    """POST /analyze with raw bytes wrapped in a multipart field."""
    return client.post(
        "/analyze",
        files={"file": (filename, BytesIO(data), "image/png")},
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_200(self):
        client = _make_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_body_is_ok(self):
        client = _make_client()
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /analyze — happy path
# ---------------------------------------------------------------------------


class TestAnalyzeHappyPath:
    def test_returns_200_on_valid_png(self):
        client = _make_client()
        resp = _upload(client, _PNG_BYTES)
        assert resp.status_code == 200

    def test_returns_200_on_valid_jpeg(self):
        client = _make_client()
        resp = _upload(client, _JPEG_BYTES, filename="meal.jpg")
        assert resp.status_code == 200

    def test_meal_recognized_true(self):
        client = _make_client()
        resp = _upload(client, _PNG_BYTES)
        assert resp.json()["meal_recognized"] is True

    def test_ingredients_present(self):
        client = _make_client()
        resp = _upload(client, _PNG_BYTES)
        assert len(resp.json()["ingredients"]) == 3

    def test_totals_present(self):
        client = _make_client()
        resp = _upload(client, _PNG_BYTES)
        totals = resp.json()["totals"]
        assert "kcal" in totals
        assert totals["kcal"] > 0

    def test_result_saved_to_history(self):
        repo = _InMemoryRepo()
        client = _make_client(repo=repo)
        _upload(client, _PNG_BYTES)
        assert len(repo._records) == 1


# ---------------------------------------------------------------------------
# POST /analyze — no meal recognized
# ---------------------------------------------------------------------------


class TestAnalyzeNoMeal:
    def test_meal_recognized_false(self):
        no_meal_vlm = FakeVLM(
            payload={"meal_recognized": False, "ingredients": []}
        )
        client = _make_client(vlm=no_meal_vlm)
        resp = _upload(client, _PNG_BYTES)
        assert resp.status_code == 200
        assert resp.json()["meal_recognized"] is False

    def test_ingredients_empty_when_no_meal(self):
        no_meal_vlm = FakeVLM(
            payload={"meal_recognized": False, "ingredients": []}
        )
        client = _make_client(vlm=no_meal_vlm)
        resp = _upload(client, _PNG_BYTES)
        assert resp.json()["ingredients"] == []


# ---------------------------------------------------------------------------
# POST /analyze — validation errors
# ---------------------------------------------------------------------------


class TestAnalyzeValidation:
    def test_rejects_non_image_bytes(self):
        client = _make_client()
        resp = _upload(client, b"this is not an image")
        assert resp.status_code == 422

    def test_rejects_empty_bytes(self):
        client = _make_client()
        resp = _upload(client, b"")
        assert resp.status_code == 422

    def test_rejects_oversized_upload(self, monkeypatch):
        from foodanalyzer.validation import ValidationError
        import foodanalyzer.api as api_module

        def _always_too_large(data, filename, max_bytes):
            raise ValidationError("Upload too large: 99.0 MB (limit 5 MB): meal.png")

        monkeypatch.setattr(api_module, "validate_image_bytes", _always_too_large)
        client = _make_client()
        resp = _upload(client, _PNG_BYTES)
        assert resp.status_code == 422

    def test_missing_file_field_returns_422(self):
        client = _make_client()
        resp = client.post("/analyze")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------


def _make_record(n: int) -> AnalysisRecord:
    return AnalysisRecord(
        id=n,
        created_at=datetime(2026, 5, 21, n, 0, tzinfo=timezone.utc),
        image_path=f"uploads/meal_{n}.png",
        ingredients=[
            IngredientOut(
                name="broccoli",
                estimated_grams=80.0,
                confidence=0.8,
                kcal=27.2,
                protein_g=2.2,
                carbs_g=5.6,
                fat_g=0.3,
            )
        ],
        totals=TotalsOut(kcal=27.2, protein_g=2.2, carbs_g=5.6, fat_g=0.9),
    )


class TestHistory:
    def test_empty_history_returns_empty_items(self):
        client = _make_client(repo=_InMemoryRepo())
        resp = client.get("/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["page"]["returned"] == 0

    def test_returns_saved_records(self):
        repo = _InMemoryRepo([_make_record(1), _make_record(2)])
        client = _make_client(repo=repo)
        resp = client.get("/history")
        assert len(resp.json()["items"]) == 2

    def test_limit_query_param(self):
        repo = _InMemoryRepo([_make_record(i) for i in range(5)])
        client = _make_client(repo=repo)
        resp = client.get("/history?limit=2")
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["page"]["limit"] == 2

    def test_offset_query_param(self):
        repo = _InMemoryRepo([_make_record(i) for i in range(5)])
        client = _make_client(repo=repo)
        resp = client.get("/history?limit=2&offset=2")
        body = resp.json()
        assert body["page"]["offset"] == 2
        assert len(body["items"]) <= 2

    def test_has_more_true_when_more_records_exist(self):
        repo = _InMemoryRepo([_make_record(i) for i in range(5)])
        client = _make_client(repo=repo)
        resp = client.get("/history?limit=2")
        assert resp.json()["page"]["has_more"] is True

    def test_has_more_false_on_last_page(self):
        repo = _InMemoryRepo([_make_record(1), _make_record(2)])
        client = _make_client(repo=repo)
        resp = client.get("/history?limit=10")
        assert resp.json()["page"]["has_more"] is False

    def test_page_metadata_present(self):
        client = _make_client(repo=_InMemoryRepo())
        resp = client.get("/history")
        page = resp.json()["page"]
        assert "limit" in page
        assert "offset" in page
        assert "returned" in page
        assert "has_more" in page

    def test_limit_above_100_rejected(self):
        client = _make_client()
        resp = client.get("/history?limit=101")
        assert resp.status_code == 422

    def test_negative_offset_rejected(self):
        client = _make_client()
        resp = client.get("/history?offset=-1")
        assert resp.status_code == 422
