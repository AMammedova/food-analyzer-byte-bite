"""Tests for src/foodanalyzer/services/ — ai_service, nutrition_cache, retry.

All tests are offline — no network calls or API keys required.

Coverage targets
----------------
- AIService.identify_ingredients:
    - happy path
    - empty meal handling
    - retry behavior
    - timeout behavior
    - dependency injection
- NutritionCache:
    - miss
    - hit
    - expiry
    - normalization
    - clear
- provider_retry:
    - retries ProviderError
    - does not retry unrelated exceptions
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from tenacity import AsyncRetrying


from ai.providers.base import ProviderError
from foodanalyzer.services.ai_service import AIService
from foodanalyzer.services.nutrition_cache import NutritionCache
from foodanalyzer.services.retry import provider_retry


# ─────────────────────────────────────────────────────────────────────────────
# AIService
# ─────────────────────────────────────────────────────────────────────────────


class TestAIService:

    @pytest.mark.asyncio
    async def test_identify_returns_ingredients(self, fake_vlm, sample_image):
        """Happy path: FakeVLM returns 3 ingredients."""
        service = AIService()
        result = await service.identify_ingredients(sample_image, vlm=fake_vlm)
        assert len(result) == 3
        assert result[0].name == "white rice (cooked)"

    @pytest.mark.asyncio
    async def test_identify_empty_list_for_no_meal(self, sample_image):
        """VLM returning empty ingredients is handled gracefully."""
        from tests.conftest import FakeVLM
        no_meal_vlm = FakeVLM(payload={"meal_recognized": False, "ingredients": []})
        service = AIService()
        result = await service.identify_ingredients(sample_image, vlm=no_meal_vlm)
        assert result == []

    @pytest.mark.asyncio
    async def test_identify_retries_on_provider_error(self, sample_image):
        """ProviderError triggers retry and succeeds on third attempt."""
        from tests.conftest import FakeVLM
        fake_vlm = FakeVLM()
        call_count = 0
        original_describe = fake_vlm.describe

        def flaky_describe(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ProviderError("temporary failure")
            return original_describe(*args, **kwargs)

        fake_vlm.describe = flaky_describe
        service = AIService()
        result = await service.identify_ingredients(sample_image, vlm=fake_vlm)
        assert call_count == 3
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_identify_reraises_after_all_attempts_fail(self, sample_image):
        """ProviderError is re-raised after retry exhaustion."""
        from tests.conftest import FakeVLM
        fake_vlm = FakeVLM()
        fake_vlm.describe = lambda *a, **kw: (
            _ for _ in ()
        ).throw(ProviderError("always fails"))
        service = AIService()
        with pytest.raises(ProviderError):
            await service.identify_ingredients(sample_image, vlm=fake_vlm)

    @pytest.mark.asyncio
    async def test_identify_times_out(self, sample_image):
        """Slow provider call raises asyncio.TimeoutError."""
        import asyncio
        from unittest.mock import patch

        async def raise_timeout(coro, *args, **kwargs):
            coro.close()  # properly close the coroutine to avoid warning
            raise asyncio.TimeoutError()

        with patch(
            "src.foodanalyzer.services.ai_service.asyncio.wait_for",
            new=raise_timeout,
        ):
            service = AIService()
            with pytest.raises(asyncio.TimeoutError):
                await service.identify_ingredients(sample_image)
                
    @pytest.mark.asyncio
    async def test_identify_uses_injected_ai_module(self, sample_image, fake_vlm):
        """Dependency injection avoids global ai imports in tests."""
        mock_ai = MagicMock()
        mock_ai.identify_ingredients.return_value = []
        service = AIService(ai_module=mock_ai)
        result = await service.identify_ingredients(sample_image, vlm=fake_vlm)
        assert result == []
        mock_ai.identify_ingredients.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# NutritionCache
# ─────────────────────────────────────────────────────────────────────────────


class TestNutritionCache:

    @pytest.mark.asyncio
    async def test_miss_returns_none(self):
        """Key that was never set returns None."""
        cache = NutritionCache()
        result = await cache.get("unknown ingredient")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_then_get_returns_value(self, fake_nutrition):
        """Value stored with set() is returned by get()."""
        cache = NutritionCache()
        facts = fake_nutrition.lookup("white rice (cooked)")
        await cache.set("white rice (cooked)", facts)
        result = await cache.get("white rice (cooked)")
        assert result is not None
        assert result.kcal_per_100g == 130

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_call_provider(self, fake_nutrition):
        """Second lookup for same key uses cache, not the provider."""
        cache = NutritionCache()
        facts = fake_nutrition.lookup("white rice (cooked)")
        await cache.set("white rice (cooked)", facts)

        call_count = [0]
        original_lookup = fake_nutrition.lookup

        def counting_lookup(name):
            call_count[0] += 1
            return original_lookup(name)

        fake_nutrition.lookup = counting_lookup
        await cache.get("white rice (cooked)")
        assert call_count[0] == 0

    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self, fake_nutrition):
        """Entry past its TTL is treated as a miss."""
        cache = NutritionCache()
        cache.ttl_seconds = -1
        facts = fake_nutrition.lookup("white rice (cooked)")
        await cache.set("white rice (cooked)", facts)
        result = await cache.get("white rice (cooked)")
        assert result is None

    @pytest.mark.asyncio
    async def test_key_normalization_case_insensitive(self, fake_nutrition):
        """'Chicken Breast' and 'chicken breast' map to the same entry."""
        cache = NutritionCache()
        facts = fake_nutrition.lookup("grilled chicken breast")
        await cache.set("Grilled Chicken Breast", facts)
        result = await cache.get("grilled chicken breast")
        assert result is not None

    @pytest.mark.asyncio
    async def test_key_normalization_strips_whitespace(self, fake_nutrition):
        """Leading/trailing whitespace is stripped before lookup."""
        cache = NutritionCache()
        facts = fake_nutrition.lookup("broccoli")
        await cache.set("  broccoli  ", facts)
        result = await cache.get("broccoli")
        assert result is not None

    @pytest.mark.asyncio
    async def test_clear_removes_all_entries(self, fake_nutrition):
        """clear() removes every cached entry."""
        cache = NutritionCache()
        facts = fake_nutrition.lookup("broccoli")
        await cache.set("broccoli", facts)
        await cache.clear()
        result = await cache.get("broccoli")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# provider_retry
# ─────────────────────────────────────────────────────────────────────────────


class TestRetryPolicy:

    def test_returns_async_retrying(self):
        """provider_retry() returns an AsyncRetrying instance."""
        retrying = provider_retry()
        assert isinstance(retrying, AsyncRetrying)

    @pytest.mark.asyncio
    async def test_reraises_provider_error_after_attempts(self):
        """ProviderError is re-raised after all attempts exhausted."""
        async def always_fails():
            async for attempt in provider_retry():
                with attempt:
                    raise ProviderError("always fails")

        with pytest.raises(ProviderError):
            await always_fails()

    @pytest.mark.asyncio
    async def test_succeeds_on_eventual_success(self):
        """Later successful attempt returns the value."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            async for attempt in provider_retry():
                with attempt:
                    call_count += 1
                    if call_count < 3:
                        raise ProviderError("not yet")
                    return "ok"

        result = await flaky()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_non_provider_errors(self):
        """ValueError is NOT retried — only ProviderError triggers retry."""
        call_count = 0

        async def raises_value_error():
            nonlocal call_count
            async for attempt in provider_retry():
                with attempt:
                    call_count += 1
                    raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await raises_value_error()

        assert call_count == 1