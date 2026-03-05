"""Shared fixtures for rebuilder-redis-module tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest

from rebuilder_redis.client import RedisClient
from rebuilder_redis.config import RedisSettings


@pytest.fixture
def redis_settings() -> RedisSettings:
    """Return default RedisSettings for testing."""
    return RedisSettings(host="localhost", port=6379, db=0)


@pytest.fixture
async def fake_redis() -> fakeredis.aioredis.FakeRedis:
    """Provide a standalone FakeRedis instance (async, decode_responses=True)."""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r  # type: ignore[misc]
    await r.aclose()


@pytest.fixture
async def redis_client(
    redis_settings: RedisSettings,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> RedisClient:
    """Provide a RedisClient wired to a FakeRedis backend.

    We patch `connect` to inject the fake and `close` to tear it down,
    so the client behaves exactly as in production minus the real server.
    """
    client = RedisClient(redis_settings)
    # Inject the fake directly — bypass real pool creation.
    client._redis = fake_redis  # noqa: SLF001
    client._pool = None  # noqa: SLF001

    # Patch close so it only resets references (the fixture handles FakeRedis cleanup).
    original_close = client.close

    async def _fake_close() -> None:
        client._redis = None  # noqa: SLF001
        client._pool = None  # noqa: SLF001

    client.close = _fake_close  # type: ignore[assignment]

    yield client  # type: ignore[misc]

    # Ensure resources are released even if the test forgets.
    client._redis = None  # noqa: SLF001
