"""Concurrent nutrition lookup pipeline.

What this module does
---------------------
Given a list of ingredient names, fetches nutrition facts for all of them
concurrently instead of one by one.

Why concurrency matters here
----------------------------
Each USDA lookup is a network I/O call (~0.5-2s). A meal with 5 ingredients
would take 5-10s sequentially. With asyncio concurrency all 5 lookups run
at the same time, completing in roughly the time of a single call.

This is concurrency (one thread, many I/O tasks in flight via asyncio),
not parallelism (multiple CPU threads). The distinction matters because
USDA lookups are I/O-bound, not CPU-bound — asyncio is the right tool.

Concurrency design
------------------
- asyncio.Semaphore(max_parallel) caps how many USDA calls are in flight
  at once. Default 10 handles any realistic meal (3-6 ingredients) fully
  concurrently while protecting against rate limiting on large batches.
  Semaphore(1) = sequential. Semaphore(100) = risks 429 on burst traffic.

- Cache check happens BEFORE acquiring the semaphore so cache hits do not
  consume a concurrency slot unnecessarily.

- asyncio.wait_for(timeout=20) prevents a hung USDA request from holding
  a semaphore slot forever and blocking other lookups.

- Only (asyncio.TimeoutError, ProviderError) are caught — operational
  failures expected in production. Programming bugs surface immediately
  instead of silently becoming None.

- Returns dict[str, NutritionFacts | None] so callers filter by value
  instead of checking for Exception instances in a list.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ai.providers.base import ProviderError
from foodanalyzer.services.retry import provider_retry

logger = logging.getLogger(__name__)


class NutritionPipeline:
    """Fetch nutrition facts for multiple ingredients concurrently."""

    def __init__(
        self,
        provider,
        cache,
        max_parallel: int = 10,
    ) -> None:
        """
        Parameters
        ----------
        provider:
            Any NutritionProvider (USDAProvider or FakeNutrition in tests).
        cache:
            A NutritionCache instance for TTL caching of results.
        max_parallel:
            Maximum concurrent USDA calls. Controlled by Semaphore.
        """
        self.provider = provider
        self.cache = cache
        self.semaphore = asyncio.Semaphore(max_parallel)

    async def _lookup_one(
        self,
        ingredient_name: str,
    ) -> tuple[str, Any | None]:
        """Look up one ingredient, using cache if available.

        Cache is checked before acquiring the semaphore so cache hits
        do not consume a concurrency slot.

        Returns
        -------
        tuple[str, NutritionFacts | None]
            (ingredient_name, facts) — None on failure so callers can
            filter rather than catching exceptions.
        """
        # Check cache BEFORE acquiring semaphore —
        # cache hits don't consume concurrency budget.
        cached = await self.cache.get(ingredient_name)
        if cached is not None:
            return ingredient_name, cached

        async with self.semaphore:
            logger.info(
                "nutrition_lookup_started",
                extra={"ingredient": ingredient_name},
            )

            try:
                async for attempt in provider_retry():
                    with attempt:
                        nutrition = await asyncio.wait_for(
                            asyncio.to_thread(
                                self.provider.lookup,
                                ingredient_name,
                            ),
                            timeout=20,
                        )

                await self.cache.set(ingredient_name, nutrition)

                logger.info(
                    "nutrition_lookup_completed",
                    extra={"ingredient": ingredient_name},
                )

                return ingredient_name, nutrition

            except (asyncio.TimeoutError, ProviderError) as exc:
                logger.warning(
                    "nutrition_lookup_failed",
                    extra={
                        "ingredient": ingredient_name,
                        "error": str(exc),
                    },
                )
                return ingredient_name, None

    async def fetch_all_nutrition(
        self,
        ingredient_names: list[str],
    ) -> dict[str, Any | None]:
        """Fetch nutrition for all ingredients concurrently.

        Parameters
        ----------
        ingredient_names:
            List of ingredient name strings from identify_ingredients().

        Returns
        -------
        dict[str, NutritionFacts | None]
            Keyed by ingredient name. None value means the lookup failed.
            Caller should filter: {k: v for k, v in facts.items() if v}
        """
        if not ingredient_names:
            return {}

        tasks = [self._lookup_one(name) for name in ingredient_names]
        results = await asyncio.gather(*tasks)

        return {
            ingredient: nutrition
            for ingredient, nutrition in results
        }