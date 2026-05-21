"""Tests for foodanalyzer.core.analyzer.analyze().

All tests use --offline-style fake providers injected via the vlm= and
nutrition= parameters. No real API calls, no network, no API keys needed.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from ai.providers.base import ProviderError, VLMProvider
from ai.nutrition import NutritionProvider
from ai.schemas import NutritionFacts

from foodanalyzer.validation import ValidationError


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

def _nf(name: str) -> NutritionFacts:
    return NutritionFacts(
        name=name,
        kcal_per_100g=100.0,
        protein_g_per_100g=10.0,
        carbs_g_per_100g=10.0,
        fat_g_per_100g=1.0,
        source="test",
    )


class _FakeVLM(VLMProvider):
    def __init__(self, payload: dict):
        self._payload = payload

    def describe(self, image_path: str, prompt: str, *, json_schema=None) -> str:
        return json.dumps(self._payload)


class _FakeNutrition(NutritionProvider):
    def __init__(self, db: dict[str, NutritionFacts]):
        self._db = db

    def lookup(self, ingredient_name: str) -> NutritionFacts:
        if ingredient_name not in self._db:
            raise ProviderError(f"missing: {ingredient_name}")
        return self._db[ingredient_name]


def _meal_vlm(*names: str) -> _FakeVLM:
    """VLM that returns recognized meal with given ingredient names."""
    return _FakeVLM({
        "meal_recognized": True,
        "ingredients": [
            {"name": n, "estimated_grams": 100.0, "confidence": 0.9}
            for n in names
        ],
    })


def _no_meal_vlm() -> _FakeVLM:
    """VLM that says no meal recognized."""
    return _FakeVLM({"meal_recognized": False, "ingredients": []})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_meal_recognized(tmp_path: Path):
    img = tmp_path / "food.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)

    vlm = _meal_vlm("rice")
    nut = _FakeNutrition({"rice": _nf("rice")})

    from foodanalyzer.core.analyzer import analyze
    result = await analyze(img, vlm=vlm, nutrition=nut)

    assert result.meal_recognized is True
    assert len(result.ingredients) == 1
    assert result.ingredients[0].name == "rice"
    assert result.totals.kcal == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_analyze_no_meal(tmp_path: Path):
    img = tmp_path / "empty.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)

    from foodanalyzer.core.analyzer import analyze
    result = await analyze(img, vlm=_no_meal_vlm(), nutrition=_FakeNutrition({}))

    assert result.meal_recognized is False
    assert result.ingredients == []
    assert result.totals.kcal == 0.0


@pytest.mark.asyncio
async def test_analyze_missing_nutrition_skipped(tmp_path: Path):
    """Ingredient with no nutrition entry is silently skipped in totals."""
    img = tmp_path / "mystery.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)

    vlm = _meal_vlm("known", "unknown")
    nut = _FakeNutrition({"known": _nf("known")})

    from foodanalyzer.core.analyzer import analyze
    result = await analyze(img, vlm=vlm, nutrition=nut)

    assert result.meal_recognized is True
    assert result.totals.kcal == pytest.approx(100.0)
    assert len(result.ingredients) == 2
    unknown_row = next(i for i in result.ingredients if i.name == "unknown")
    assert unknown_row.kcal == 0.0


@pytest.mark.asyncio
async def test_analyze_invalid_image_raises(tmp_path: Path):
    img = tmp_path / "not_image.txt"
    img.write_bytes(b"hello world")

    from foodanalyzer.core.analyzer import analyze
    with pytest.raises(ValidationError):
        await analyze(img, vlm=_no_meal_vlm(), nutrition=_FakeNutrition({}))


@pytest.mark.asyncio
async def test_analyze_missing_file_raises(tmp_path: Path):
    img = tmp_path / "ghost.jpg"

    from foodanalyzer.core.analyzer import analyze
    with pytest.raises(ValidationError):
        await analyze(img, vlm=_no_meal_vlm(), nutrition=_FakeNutrition({}))


# ---------------------------------------------------------------------------
# Dependency injection — AIService and NutritionPipeline overrides
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_uses_injected_ai_service(tmp_path: Path):
    """An explicit AIService passed in is used instead of building a default."""
    from foodanalyzer.core.analyzer import analyze
    from foodanalyzer.services.ai_service import AIService

    img = tmp_path / "food.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)

    vlm = _meal_vlm("rice")
    nut = _FakeNutrition({"rice": _nf("rice")})
    custom_service = AIService()

    result = await analyze(img, vlm=vlm, nutrition=nut, ai_service=custom_service)
    assert result.meal_recognized is True
    assert result.totals.kcal == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_analyze_uses_injected_pipeline(tmp_path: Path):
    """A pre-built NutritionPipeline is honored instead of building a new one.

    The injected pipeline owns its own cache, so calling analyze twice with
    the same shared pipeline + provider should populate the cache after the
    first call.
    """
    from foodanalyzer.concurrency.pipeline import NutritionPipeline
    from foodanalyzer.core.analyzer import analyze
    from foodanalyzer.services.nutrition_cache import NutritionCache

    img = tmp_path / "food.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)

    nut = _FakeNutrition({"rice": _nf("rice")})
    cache = NutritionCache()
    pipeline = NutritionPipeline(provider=nut, cache=cache, max_parallel=4)

    result = await analyze(img, vlm=_meal_vlm("rice"), pipeline=pipeline)
    assert result.meal_recognized is True
    assert result.totals.kcal == pytest.approx(100.0)

    cached = await cache.get("rice")
    assert cached is not None, "the shared pipeline's cache should be populated"


@pytest.mark.asyncio
async def test_analyze_concurrent_lookups_for_many_ingredients(tmp_path: Path):
    """Many ingredients are looked up concurrently and the totals are aggregated."""
    from foodanalyzer.core.analyzer import analyze

    img = tmp_path / "feast.jpg"
    img.write_bytes(b"\xff\xd8" + b"\x00" * 10)

    names = ["a", "b", "c", "d", "e"]
    vlm = _meal_vlm(*names)
    nut = _FakeNutrition({n: _nf(n) for n in names})

    result = await analyze(img, vlm=vlm, nutrition=nut)

    assert result.meal_recognized is True
    assert len(result.ingredients) == 5
    # 5 ingredients × 100g × 100 kcal/100g = 500
    assert result.totals.kcal == pytest.approx(500.0)
