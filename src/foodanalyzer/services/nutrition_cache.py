"""In-memory TTL cache for USDA nutrition lookups.

Why cache?
----------
USDA facts for standard ingredients (chicken breast, white rice) rarely
change. Caching for 24 h eliminates redundant API calls within a session
and protects against rate limiting on the free tier.

Design decisions
----------------
- The cache uses a lightweight async lock only for writes and eviction.
  Fast cache hits avoid locking entirely for better concurrency.
- Expired eviction uses an identity check before deletion to avoid
  accidentally removing a newer value written by another coroutine.
- Key normalization (strip + lower) ensures "Chicken Breast" and
  "chicken breast" hit the same entry.
- CacheEntry dataclass makes the (value, expiry) pair self-documenting
  and prevents bugs from tuple index misuse.
- TTL is read from settings so it can be overridden via env var for tests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from foodanalyzer.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached nutrition lookup result."""

    value: Any
    expires_at: float


class NutritionCache:
    """Coroutine-safe async TTL cache keyed by ingredient name."""

    def __init__(self) -> None:
        self.ttl_seconds: int = get_settings().nutrition_cache_ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _normalize_key(self, key: str) -> str:
        """Normalize ingredient names for stable cache keys."""
        return key.strip().lower()

    async def get(self, key: str) -> Any | None:
        """Return cached value or None if missing or expired."""
        normalized = self._normalize_key(key)

        entry = self._store.get(normalized)

        if entry is None:
            logger.debug(
                "nutrition_cache_miss",
                extra={"ingredient": normalized},
            )
            return None

        if time.time() > entry.expires_at:
            logger.debug(
                "nutrition_cache_expired",
                extra={"ingredient": normalized},
            )

            async with self._lock:
                # Only evict if the dict still points
                # to this same expired object instance.
                if self._store.get(normalized) is entry:
                    self._store.pop(normalized, None)

            return None

        logger.debug(
            "nutrition_cache_hit",
            extra={"ingredient": normalized},
        )

        return entry.value

    async def set(self, key: str, value: Any) -> None:
        """Store a value with a TTL expiry."""
        normalized = self._normalize_key(key)

        async with self._lock:
            self._store[normalized] = CacheEntry(
                value=value,
                expires_at=time.time() + self.ttl_seconds,
            )

        logger.debug(
            "nutrition_cache_saved",
            extra={"ingredient": normalized},
        )

    async def clear(self) -> None:
        """Remove all cache entries. Useful in tests."""
        async with self._lock:
            self._store.clear()