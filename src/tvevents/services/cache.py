"""Blacklist cache service — Redis-backed, with RDS fallback.

Replaces the legacy file-based cache (``/tmp/.blacklisted_channel_ids_cache``)
with a shared Redis SET that is visible across all pods and survives restarts.
Uses the ``rebuilder_redis`` module for Redis operations.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

if TYPE_CHECKING:
    from tvevents.config import Settings
    from tvevents.services.rds_client import RdsClient

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_REDIS_KEY = "tvevents:blacklisted_channel_ids"


class BlacklistCacheService:
    """TTL-based blacklist cache — Redis primary, RDS fallback."""

    def __init__(
        self,
        settings: Settings,
        rds_client: RdsClient,
        redis_client: Any,
    ) -> None:
        self._settings = settings
        self._rds = rds_client
        self._redis = redis_client
        self._last_refresh: float = 0.0

    # ── Public API ───────────────────────────────────────────────────────

    async def get_blacklisted_channels(self) -> set[str]:
        """Return the full set of blacklisted channel IDs.

        1. Check Redis first.
        2. If Redis is empty / unavailable, fetch from RDS and update Redis.
        """
        with tracer.start_as_current_span("cache.get_blacklisted_channels"):
            try:
                members = await self._redis.smembers(_REDIS_KEY)
                if members:
                    return {m.decode() if isinstance(m, bytes) else str(m) for m in members}
            except Exception as exc:
                logger.warning("Redis read failed, falling back to RDS: %s", exc)

            return await self.refresh_cache()

    async def refresh_cache(self) -> set[str]:
        """Force-refresh the cache from RDS and update Redis."""
        with tracer.start_as_current_span("cache.refresh"):
            channel_ids = await self._rds.fetch_blacklisted_channel_ids()
            id_set = set(channel_ids)

            try:
                pipe = self._redis.pipeline()
                await pipe.delete(_REDIS_KEY)
                if id_set:
                    await pipe.sadd(_REDIS_KEY, *id_set)
                    await pipe.expire(_REDIS_KEY, self._settings.blacklist_cache_ttl)
                await pipe.execute()
                self._last_refresh = time.monotonic()
                logger.info(
                    "Blacklist cache refreshed: %d channel IDs, TTL=%ds",
                    len(id_set),
                    self._settings.blacklist_cache_ttl,
                )
            except Exception as exc:
                logger.error("Redis write failed during cache refresh: %s", exc)

            return id_set

    async def is_blacklisted(self, channel_id: str) -> bool:
        """Check whether *channel_id* is in the blacklist.

        Performs a Redis ``SISMEMBER`` for O(1) lookup. Falls back to a
        full set fetch if Redis is unavailable.
        """
        with tracer.start_as_current_span("cache.is_blacklisted") as span:
            span.set_attribute("channel_id", channel_id)
            try:
                result = await self._redis.sismember(_REDIS_KEY, channel_id)
                if result is not None:
                    return bool(result)
            except Exception as exc:
                logger.warning(
                    "Redis SISMEMBER failed for channel %s, falling back: %s",
                    channel_id,
                    exc,
                )

            # Fallback: full set from RDS
            full_set = await self.get_blacklisted_channels()
            return channel_id in full_set

    async def flush_cache(self) -> None:
        """Delete the Redis key to force a re-fetch on next access."""
        with tracer.start_as_current_span("cache.flush"):
            try:
                await self._redis.delete(_REDIS_KEY)
                logger.info("Blacklist cache flushed")
            except Exception as exc:
                logger.error("Failed to flush blacklist cache: %s", exc)
                raise

    @property
    def seconds_since_refresh(self) -> float:
        """Seconds since the last successful cache refresh."""
        if self._last_refresh == 0.0:
            return float("inf")
        return time.monotonic() - self._last_refresh
