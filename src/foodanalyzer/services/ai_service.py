"""AI service wrapper — retries, timeout, and structured logging.

This module is the ONLY place that calls ai.identify_ingredients().
Business logic (analyzer.py, api.py, cli.py) must never import from
ai/ directly — they go through AIService.

Design decisions
----------------
- Class-based so dependencies can be injected in tests.
- asyncio.wait_for(timeout=60) prevents provider hangs from
  blocking requests forever.
- asyncio.to_thread() safely wraps sync provider SDK calls.
- Retry logic is centralized in retry.py via AsyncRetrying.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import ai

from src.foodanalyzer.services.retry import provider_retry

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 60


class AIService:
    """Wrapper around ai.identify_ingredients with retry and timeout."""

    def __init__(self, ai_module: Any = ai) -> None:
        """
        Parameters
        ----------
        ai_module:
            Injectable dependency for tests.
            Defaults to the real ai module.
        """
        self._ai = ai_module

    async def identify_ingredients(
        self,
        image_path: str,
        vlm: Any = None,
    ) -> list:
        """Identify ingredients from a meal image.

        Parameters
        ----------
        image_path:
            Path to the uploaded image.

        vlm:
            Optional provider override for tests/custom providers.

        Returns
        -------
        list
            List of Ingredient objects.
            Empty list means "unknown meal".

        Raises
        ------
        ProviderError
            Raised after retry exhaustion.

        asyncio.TimeoutError
            Raised if provider exceeds timeout.
        """

        async for attempt in provider_retry():
            with attempt:
                logger.info(
                    "ingredient_identification_started",
                    extra={
                        "image_path": image_path,
                    },
                )

                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._ai.identify_ingredients,
                        image_path,
                        vlm,
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )

                ingredient_count = len(result) if result else 0

                logger.info(
                    "ingredient_identification_completed",
                    extra={
                        "ingredient_count": ingredient_count,
                    },
                )

                return result