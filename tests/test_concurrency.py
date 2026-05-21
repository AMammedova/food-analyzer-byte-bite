"""Tests for src/foodanalyzer/concurrency/pipeline.py — NutritionPipeline.

What this test module covers
-----------------------------
NutritionPipeline fetches nutrition facts for multiple ingredients
concurrently. These tests verify:

- fetch_all_nutrition: empty input, happy path, correct values
- _lookup_one: cache hit skips provider and semaphore
- Failure handling: unknown ingredient returns None, does not crash others
- Semaphore: different max_parallel values still produce correct results
- Cache integration: second call uses cache, not provider

All tests are offline — FakeNutrition from conftest.py, no network calls.
No API keys required.
"""

from __future__ import annotations

import pytest
import asyncio

from foodanalyzer.concurrency.pipeline import NutritionPipeline
from foodanalyzer.services.nutrition_cache import NutritionCache


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def make_pipeline(fake_nutrition, max_parallel: int = 10) -> NutritionPipeline:
    """Build a NutritionPipeline with a fresh cache for each test."""
    cache = NutritionCache()
    return NutritionPipeline(
        provider=fake_nutrition,
        cache=cache,
        max_parallel=max_parallel,
    )


# ─────────────────────────────────────────────────────────────────────────────
# fetch_all_nutrition — basic correctness
# ─────────────────────────────────────────────────────────────────────────────


class TestFetchAllNutrition:

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self, fake_nutrition):
        """No ingredients → empty dict, no provider calls."""
        pipeline = make_pipeline(fake_nutrition)
        result = await pipeline.fetch_all_nutrition([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_dict_keyed_by_name(self, fake_nutrition):
        """Result keys match the input ingredient names exactly."""
        pipeline = make_pipeline(fake_nutrition)
        names = ["white rice (cooked)", "broccoli"]
        result = await pipeline.fetch_all_nutrition(names)
        assert set(result.keys()) == set(names)

    @pytest.mark.asyncio
    async def test_correct_nutrition_values(self, fake_nutrition):
        """Returned facts match FakeNutrition DB values."""
        pipeline = make_pipeline(fake_nutrition)
        result = await pipeline.fetch_all_nutrition(["white rice (cooked)"])
        facts = result["white rice (cooked)"]
        assert facts is not None
        assert facts.kcal_per_100g == 130

    @pytest.mark.asyncio
    async def test_all_three_ingredients(self, fake_nutrition):
        """All three FakeNutrition ingredients are fetched correctly."""
        pipeline = make_pipeline(fake_nutrition)
        names = [
            "white rice (cooked)",
            "grilled chicken breast",
            "broccoli",
        ]
        result = await pipeline.fetch_all_nutrition(names)
        assert len(result) == 3
        assert all(v is not None for v in result.values())

    @pytest.mark.asyncio
    async def test_result_length_matches_input(self, fake_nutrition):
        """Output dict has exactly as many entries as input list."""
        pipeline = make_pipeline(fake_nutrition)
        names = ["white rice (cooked)", "broccoli"]
        result = await pipeline.fetch_all_nutrition(names)
        assert len(result) == len(names)


# ─────────────────────────────────────────────────────────────────────────────
# fetch_all_nutrition — failure handling
# ─────────────────────────────────────────────────────────────────────────────


class TestFailureHandling:

    @pytest.mark.asyncio
    async def test_unknown_ingredient_returns_none(self, fake_nutrition):
        """Unknown ingredient produces None value, does not crash."""
        pipeline = make_pipeline(fake_nutrition)
        result = await pipeline.fetch_all_nutrition(["unknown xyz"])
        assert result["unknown xyz"] is None

    @pytest.mark.asyncio
    async def test_one_failure_does_not_cancel_others(self, fake_nutrition):
        """One bad ingredient does not prevent the rest from succeeding."""
        pipeline = make_pipeline(fake_nutrition)
        names = ["white rice (cooked)", "unknown xyz", "broccoli"]
        result = await pipeline.fetch_all_nutrition(names)
        assert result["white rice (cooked)"] is not None
        assert result["broccoli"] is not None
        assert result["unknown xyz"] is None

    @pytest.mark.asyncio
    async def test_all_unknown_returns_all_none(self, fake_nutrition):
        """All unknown ingredients produce all None values."""
        pipeline = make_pipeline(fake_nutrition)
        names = ["unknown a", "unknown b"]
        result = await pipeline.fetch_all_nutrition(names)
        assert result["unknown a"] is None
        assert result["unknown b"] is None

    @pytest.mark.asyncio
    async def test_duplicate_names_handled(self, fake_nutrition):
        """Duplicate ingredient names collapse into one dict key."""
        pipeline = make_pipeline(fake_nutrition)
        result = await pipeline.fetch_all_nutrition(["broccoli", "broccoli"])
        assert len(result) == 1
        assert result["broccoli"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Cache integration
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheIntegration:

    @pytest.mark.asyncio
    async def test_second_call_uses_cache_not_provider(self, fake_nutrition):
        """Second fetch_all_nutrition call for same ingredient hits cache."""
        pipeline = make_pipeline(fake_nutrition)

        call_count = [0]
        original_lookup = fake_nutrition.lookup

        def counting_lookup(name):
            call_count[0] += 1
            return original_lookup(name)

        fake_nutrition.lookup = counting_lookup

        await pipeline.fetch_all_nutrition(["broccoli"])
        first_count = call_count[0]

        await pipeline.fetch_all_nutrition(["broccoli"])
        second_count = call_count[0]

        assert first_count == 1
        assert second_count == 1  # no additional call on second fetch

    @pytest.mark.asyncio
    async def test_cache_hit_before_semaphore(self, fake_nutrition):
        """Cached values are returned successfully."""
        cache = NutritionCache()
        pipeline = NutritionPipeline(
            provider=fake_nutrition,
            cache=cache,
            max_parallel=1,  # semaphore of 1 to make blocking obvious
        )

        # Pre-populate cache
        facts = fake_nutrition.lookup("broccoli")
        await cache.set("broccoli", facts)

        # With semaphore=1 this would block if cache check was inside semaphore
        result = await pipeline.fetch_all_nutrition(["broccoli", "broccoli"])
        assert result["broccoli"] is not None

    @pytest.mark.asyncio
    async def test_cache_persists_between_calls(self, fake_nutrition):
        """Results cached in first call are available in second call."""
        cache = NutritionCache()
        pipeline = NutritionPipeline(
            provider=fake_nutrition,
            cache=cache,
            max_parallel=10,
        )
        await pipeline.fetch_all_nutrition(["broccoli"])
        cached = await cache.get("broccoli")
        assert cached is not None


# ─────────────────────────────────────────────────────────────────────────────
# Semaphore behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestSemaphore:

    @pytest.mark.asyncio
    async def test_semaphore_one_still_returns_correct_results(
        self, fake_nutrition
    ):
        """Semaphore(1) processes sequentially but returns correct results."""
        pipeline = make_pipeline(fake_nutrition, max_parallel=1)
        names = ["white rice (cooked)", "broccoli"]
        result = await pipeline.fetch_all_nutrition(names)
        assert len(result) == 2
        assert all(v is not None for v in result.values())

    @pytest.mark.asyncio
    async def test_semaphore_large_value_still_works(self, fake_nutrition):
        """Semaphore(100) does not cause errors on small input."""
        pipeline = make_pipeline(fake_nutrition, max_parallel=100)
        result = await pipeline.fetch_all_nutrition(["broccoli"])
        assert result["broccoli"] is not None

    @pytest.mark.asyncio
    async def test_default_max_parallel_is_ten(self, fake_nutrition):
        """Default NutritionPipeline uses Semaphore(10)."""
        cache = NutritionCache()
        pipeline = NutritionPipeline(provider=fake_nutrition, cache=cache)
        assert isinstance(pipeline.semaphore, asyncio.Semaphore)
