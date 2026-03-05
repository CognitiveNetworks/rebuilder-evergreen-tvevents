"""Tests for RedisClient operations."""

from __future__ import annotations

import pytest

from rebuilder_redis.client import RedisClient
from rebuilder_redis.config import RedisSettings
from rebuilder_redis.exceptions import RedisConnectionError, RedisOperationError


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


class TestLifecycle:
    """Connect, close, health-check, and context-manager tests."""

    async def test_health_check_returns_true(self, redis_client: RedisClient) -> None:
        result = await redis_client.health_check()
        assert result is True

    async def test_health_check_returns_false_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        # Never connected — internal _redis is None.
        assert await client.health_check() is False

    async def test_close_sets_redis_to_none(self, redis_client: RedisClient) -> None:
        await redis_client.close()
        assert redis_client._redis is None  # noqa: SLF001

    async def test_operation_after_close_raises(self, redis_client: RedisClient) -> None:
        await redis_client.close()
        with pytest.raises(RedisConnectionError, match="not connected"):
            await redis_client.get("any-key")


# --------------------------------------------------------------------------
# Key-Value operations
# --------------------------------------------------------------------------


class TestKeyValueOps:
    """GET / SET / DELETE / EXISTS / EXPIRE / TTL."""

    async def test_set_and_get(self, redis_client: RedisClient) -> None:
        assert await redis_client.set("device:AB:CD:EF:01:23:45", "active") is True
        assert await redis_client.get("device:AB:CD:EF:01:23:45") == "active"

    async def test_get_missing_key_returns_none(self, redis_client: RedisClient) -> None:
        assert await redis_client.get("nonexistent:key") is None

    async def test_set_with_ttl(self, redis_client: RedisClient) -> None:
        await redis_client.set("session:v1-fw-8.0.2", "data", ttl=120)
        remaining = await redis_client.ttl("session:v1-fw-8.0.2")
        assert 0 < remaining <= 120

    async def test_delete_existing_key(self, redis_client: RedisClient) -> None:
        await redis_client.set("temp:device-E4:F3:22:AA:BB:CC", "1")
        count = await redis_client.delete("temp:device-E4:F3:22:AA:BB:CC")
        assert count == 1

    async def test_delete_missing_key_returns_zero(self, redis_client: RedisClient) -> None:
        count = await redis_client.delete("no:such:key")
        assert count == 0

    async def test_exists_true(self, redis_client: RedisClient) -> None:
        await redis_client.set("model:P65Q9-J01", "65-inch")
        assert await redis_client.exists("model:P65Q9-J01") is True

    async def test_exists_false(self, redis_client: RedisClient) -> None:
        assert await redis_client.exists("model:DOES-NOT-EXIST") is False

    async def test_expire_sets_ttl(self, redis_client: RedisClient) -> None:
        await redis_client.set("firmware:v5.10.3", "payload")
        assert await redis_client.expire("firmware:v5.10.3", 60) is True
        remaining = await redis_client.ttl("firmware:v5.10.3")
        assert 0 < remaining <= 60

    async def test_ttl_no_expiry(self, redis_client: RedisClient) -> None:
        await redis_client.set("persistent:key", "forever")
        assert await redis_client.ttl("persistent:key") == -1

    async def test_ttl_missing_key(self, redis_client: RedisClient) -> None:
        assert await redis_client.ttl("ghost:key") == -2


# --------------------------------------------------------------------------
# Set operations
# --------------------------------------------------------------------------


class TestSetOps:
    """SADD / SREM / SMEMBERS / SISMEMBER / SCARD."""

    async def test_sadd_and_smembers(self, redis_client: RedisClient) -> None:
        added = await redis_client.sadd(
            "blacklist:mac",
            "AA:BB:CC:DD:EE:01",
            "AA:BB:CC:DD:EE:02",
            "AA:BB:CC:DD:EE:03",
        )
        assert added == 3
        members = await redis_client.smembers("blacklist:mac")
        assert members == {"AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03"}

    async def test_sadd_duplicate_not_counted(self, redis_client: RedisClient) -> None:
        await redis_client.sadd("tags:device-1", "smart-tv")
        second = await redis_client.sadd("tags:device-1", "smart-tv")
        assert second == 0

    async def test_srem(self, redis_client: RedisClient) -> None:
        await redis_client.sadd("blacklist:serial", "SN-20240101-001", "SN-20240101-002")
        removed = await redis_client.srem("blacklist:serial", "SN-20240101-001")
        assert removed == 1
        assert await redis_client.scard("blacklist:serial") == 1

    async def test_sismember_true(self, redis_client: RedisClient) -> None:
        await redis_client.sadd("allowed:regions", "US-EAST", "US-WEST", "EU-CENTRAL")
        assert await redis_client.sismember("allowed:regions", "US-EAST") is True

    async def test_sismember_false(self, redis_client: RedisClient) -> None:
        await redis_client.sadd("allowed:regions", "US-EAST")
        assert await redis_client.sismember("allowed:regions", "AP-SOUTH") is False

    async def test_scard(self, redis_client: RedisClient) -> None:
        await redis_client.sadd("features:v3", "hdr10", "dolby-vision", "atmos")
        assert await redis_client.scard("features:v3") == 3

    async def test_scard_empty_set(self, redis_client: RedisClient) -> None:
        assert await redis_client.scard("empty:set:key") == 0

    async def test_smembers_empty(self, redis_client: RedisClient) -> None:
        members = await redis_client.smembers("nonexistent:set")
        assert members == set()


# --------------------------------------------------------------------------
# Bulk / pipeline operations
# --------------------------------------------------------------------------


class TestBulkOps:
    """set_with_members atomic replace tests."""

    async def test_set_with_members_creates_set(self, redis_client: RedisClient) -> None:
        macs = {
            "11:22:33:44:55:66",
            "AA:BB:CC:DD:EE:FF",
            "00:11:22:33:44:55",
        }
        result = await redis_client.set_with_members("cache:blacklist:v2", macs, ttl=300)
        assert result is True
        stored = await redis_client.smembers("cache:blacklist:v2")
        assert stored == macs
        remaining = await redis_client.ttl("cache:blacklist:v2")
        assert 0 < remaining <= 300

    async def test_set_with_members_replaces_existing(self, redis_client: RedisClient) -> None:
        old = {"old-member-1", "old-member-2"}
        new = {"new-member-A", "new-member-B", "new-member-C"}
        await redis_client.set_with_members("replace:test", old)
        await redis_client.set_with_members("replace:test", new, ttl=60)
        stored = await redis_client.smembers("replace:test")
        assert stored == new
        assert await redis_client.scard("replace:test") == 3

    async def test_set_with_members_empty_set(self, redis_client: RedisClient) -> None:
        # Seed an existing key, then replace with empty set → key should be deleted.
        await redis_client.set_with_members("to-clear", {"a", "b"})
        result = await redis_client.set_with_members("to-clear", set())
        assert result is True
        assert await redis_client.exists("to-clear") is False

    async def test_set_with_members_no_ttl(self, redis_client: RedisClient) -> None:
        await redis_client.set_with_members("persistent:set", {"x", "y"})
        assert await redis_client.ttl("persistent:set") == -1


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------


class TestErrorHandling:
    """Ensure correct custom exceptions are raised when the client is disconnected."""

    async def test_get_raises_connection_error_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RedisConnectionError):
            await client.get("key")

    async def test_set_raises_connection_error_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RedisConnectionError):
            await client.set("key", "val")

    async def test_delete_raises_connection_error_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RedisConnectionError):
            await client.delete("key")

    async def test_sadd_raises_connection_error_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RedisConnectionError):
            await client.sadd("key", "member")

    async def test_smembers_raises_connection_error_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RedisConnectionError):
            await client.smembers("key")

    async def test_set_with_members_raises_connection_error_when_disconnected(
        self, redis_settings: RedisSettings
    ) -> None:
        client = RedisClient(redis_settings)
        with pytest.raises(RedisConnectionError):
            await client.set_with_members("key", {"a"})
