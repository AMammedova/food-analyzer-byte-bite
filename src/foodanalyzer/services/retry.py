"""Reusable async retry factory for provider calls.

All AI provider calls go through this retry config.
Defined once here so every caller shares the same backoff
policy — change it in one place, it applies everywhere.
"""

from __future__ import annotations

import logging

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai.providers.base import ProviderError

logger = logging.getLogger(__name__)


def provider_retry() -> AsyncRetrying:
    """Return a configured AsyncRetrying context manager.

    Usage
    -----
    async for attempt in provider_retry():
        with attempt:
            result = await some_provider_call()

    Policy
    ------
    - Retries only on ProviderError (transient provider failures).
    - Exponential backoff: 2s → 4s → 8s … up to 30s cap.
    - Maximum 4 attempts total (1 original + 3 retries).
    - Logs a WARNING before each sleep so the console shows progress.
    - reraise=True: after all attempts fail, the original ProviderError
      is re-raised instead of being wrapped in RetryError.
    """
    return AsyncRetrying(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(ProviderError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )