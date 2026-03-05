"""Blacklist cache lifecycle tests — Redis primary, RDS fallback.

Validates the BlacklistCacheService round-trip: Redis → RDS fallback →
refresh → flush, using realistic blacklisted channel IDs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import TEST_SALT, TEST_ZOO
from tvevents.config import Settings
from tvevents.services.cache import BlacklistCacheService


def _make_settings() -> Settings:
    return Settings(
        t1_salt=TEST_SALT,
        zoo=TEST_ZOO,
        blacklist_cache_ttl=300,
    )


def _make_redis(members: set[bytes] | None = None) -> AsyncMock:
    """Create a mock Redis client, optionally pre-populated."""
    redis = AsyncMock()
    redis.smembers = AsyncMock(return_value=members or set())
    redis.sismember = AsyncMock(
        side_effect=lambda key, val: (
            val.encode() in (members or set())
            if isinstance(val, str)
            else val in (members or set())
        )
    )
    redis.delete = AsyncMock()
    redis.ping = AsyncMock(return_value=True)

    pipe = AsyncMock()
    pipe.delete = AsyncMock()
    pipe.sadd = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.execute = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)

    return redis


def _make_rds(channel_ids: list[str] | None = None) -> AsyncMock:
    rds = AsyncMock()
    rds.fetch_blacklisted_channel_ids = AsyncMock(return_value=channel_ids or [])
    return rds


class TestBlacklistCacheLifecycle:
    """Verify the Redis ↔ RDS blacklist cache lifecycle: lookup, fallback,
    refresh, and flush operations."""

    @pytest.mark.asyncio
    async def test_cache_returns_channels_from_redis(self) -> None:
        """When Redis is populated with blacklisted channels 10501/99999,
        get_blacklisted_channels returns them without querying RDS."""
        redis = _make_redis(members={b"10501", b"99999"})
        rds = _make_rds()
        cache = BlacklistCacheService(_make_settings(), rds, redis)

        result = await cache.get_blacklisted_channels()
        assert result == {"10501", "99999"}
        rds.fetch_blacklisted_channel_ids.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_falls_back_to_rds_on_redis_miss(self) -> None:
        """When Redis is empty, the cache falls back to RDS, fetches
        channels, and populates Redis for next time."""
        redis = _make_redis(members=set())  # empty Redis
        rds = _make_rds(channel_ids=["10501", "99999"])
        cache = BlacklistCacheService(_make_settings(), rds, redis)

        result = await cache.get_blacklisted_channels()
        assert "10501" in result
        assert "99999" in result
        rds.fetch_blacklisted_channel_ids.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_is_blacklisted_returns_true_for_known_channel(self) -> None:
        """Channel 10501 is in the blacklist → is_blacklisted returns True."""
        redis = _make_redis(members={b"10501", b"99999"})
        redis.sismember = AsyncMock(return_value=True)
        rds = _make_rds()
        cache = BlacklistCacheService(_make_settings(), rds, redis)

        result = await cache.is_blacklisted("10501")
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_is_blacklisted_returns_false_for_unknown_channel(self) -> None:
        """Channel 12345 is not in the blacklist → is_blacklisted returns False."""
        redis = _make_redis(members={b"10501"})
        redis.sismember = AsyncMock(return_value=False)
        rds = _make_rds()
        cache = BlacklistCacheService(_make_settings(), rds, redis)

        result = await cache.is_blacklisted("12345")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_refresh_updates_redis_from_rds(self) -> None:
        """refresh_cache queries RDS for the latest list and writes it
        to Redis using a pipeline (delete + sadd + expire)."""
        redis = _make_redis()
        rds = _make_rds(channel_ids=["10501", "77777"])
        cache = BlacklistCacheService(_make_settings(), rds, redis)

        result = await cache.refresh_cache()
        assert result == {"10501", "77777"}
        rds.fetch_blacklisted_channel_ids.assert_awaited_once()
        # Pipeline should have been used
        redis.pipeline.assert_called()

    @pytest.mark.asyncio
    async def test_cache_flush_removes_redis_key(self) -> None:
        """flush_cache deletes the Redis key, forcing a fresh RDS fetch
        on the next access."""
        redis = _make_redis(members={b"10501"})
        rds = _make_rds()
        cache = BlacklistCacheService(_make_settings(), rds, redis)

        await cache.flush_cache()
        redis.delete.assert_awaited()
