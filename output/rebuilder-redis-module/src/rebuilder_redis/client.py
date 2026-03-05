"""Async Redis client with connection pooling, OTEL tracing, and structured logging."""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Self

import redis.asyncio as aioredis
from opentelemetry import trace
from redis.exceptions import RedisError

from rebuilder_redis.config import RedisSettings
from rebuilder_redis.exceptions import RedisConnectionError, RedisOperationError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class RedisClient:
    """Async Redis client with connection pooling, OTEL tracing, and error handling.

    Usage::

        async with RedisClient(RedisSettings()) as client:
            await client.set("key", "value", ttl=300)
            value = await client.get("key")
    """

    def __init__(self, settings: RedisSettings) -> None:
        self._settings = settings
        self._pool: aioredis.ConnectionPool | None = None
        self._redis: aioredis.Redis | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the connection pool and verify connectivity with a ping."""
        with tracer.start_as_current_span(
            "redis.connect",
            attributes={"db.system": "redis", "db.operation": "connect"},
        ):
            try:
                self._pool = aioredis.ConnectionPool(
                    host=self._settings.host,
                    port=self._settings.port,
                    db=self._settings.db,
                    password=self._settings.password,
                    socket_timeout=self._settings.socket_timeout,
                    socket_connect_timeout=self._settings.socket_connect_timeout,
                    max_connections=self._settings.max_connections,
                    decode_responses=self._settings.decode_responses,
                    retry_on_timeout=self._settings.retry_on_timeout,
                    health_check_interval=self._settings.health_check_interval,
                )
                self._redis = aioredis.Redis(connection_pool=self._pool)
                await self._redis.ping()
                logger.info(
                    "redis_connected",
                    extra={"host": self._settings.host, "port": self._settings.port},
                )
            except RedisError as exc:
                logger.error(
                    "redis_connection_failed",
                    extra={"host": self._settings.host, "error": str(exc)},
                )
                raise RedisConnectionError(
                    f"Failed to connect to Redis at {self._settings.host}:{self._settings.port}"
                ) from exc

    async def close(self) -> None:
        """Close the connection pool gracefully."""
        with tracer.start_as_current_span(
            "redis.close",
            attributes={"db.system": "redis", "db.operation": "close"},
        ):
            if self._redis is not None:
                await self._redis.aclose()
                self._redis = None
            if self._pool is not None:
                await self._pool.aclose()
                self._pool = None
            logger.info("redis_connection_closed")

    async def health_check(self) -> bool:
        """Return *True* if Redis responds to PING, *False* otherwise."""
        with tracer.start_as_current_span(
            "redis.health_check",
            attributes={"db.system": "redis", "db.operation": "ping"},
        ):
            try:
                if self._redis is None:
                    return False
                await self._redis.ping()
                return True
            except RedisError as exc:
                logger.warning("redis_health_check_failed", extra={"error": str(exc)})
                return False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> aioredis.Redis:  # type: ignore[type-arg]
        if self._redis is None:
            raise RedisConnectionError("RedisClient is not connected. Call connect() first.")
        return self._redis

    # ------------------------------------------------------------------
    # Key-Value operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        """Get the value for *key*, or *None* if not found / on error."""
        with tracer.start_as_current_span(
            "redis.get",
            attributes={
                "db.system": "redis",
                "db.operation": "GET",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                value: str | None = await client.get(key)
                return value
            except RedisError as exc:
                logger.error(
                    "redis_get_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"GET failed for key={key}") from exc

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Set *key* to *value* with an optional TTL in seconds."""
        with tracer.start_as_current_span(
            "redis.set",
            attributes={
                "db.system": "redis",
                "db.operation": "SET",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                result: bool | None = await client.set(key, value, ex=ttl)
                return result is True
            except RedisError as exc:
                logger.error(
                    "redis_set_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"SET failed for key={key}") from exc

    async def delete(self, key: str) -> int:
        """Delete *key*. Returns the number of keys removed (0 or 1)."""
        with tracer.start_as_current_span(
            "redis.delete",
            attributes={
                "db.system": "redis",
                "db.operation": "DEL",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                count: int = await client.delete(key)
                return count
            except RedisError as exc:
                logger.error(
                    "redis_delete_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"DEL failed for key={key}") from exc

    async def exists(self, key: str) -> bool:
        """Return *True* if *key* exists."""
        with tracer.start_as_current_span(
            "redis.exists",
            attributes={
                "db.system": "redis",
                "db.operation": "EXISTS",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                result: int = await client.exists(key)
                return result > 0
            except RedisError as exc:
                logger.error(
                    "redis_exists_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"EXISTS failed for key={key}") from exc

    async def expire(self, key: str, ttl: int) -> bool:
        """Set a TTL (seconds) on *key*. Returns *True* if the timeout was set."""
        with tracer.start_as_current_span(
            "redis.expire",
            attributes={
                "db.system": "redis",
                "db.operation": "EXPIRE",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                result: bool = await client.expire(key, ttl)
                return result
            except RedisError as exc:
                logger.error(
                    "redis_expire_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"EXPIRE failed for key={key}") from exc

    async def ttl(self, key: str) -> int:
        """Return remaining TTL in seconds. -1 = no expiry, -2 = key missing."""
        with tracer.start_as_current_span(
            "redis.ttl",
            attributes={
                "db.system": "redis",
                "db.operation": "TTL",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                remaining: int = await client.ttl(key)
                return remaining
            except RedisError as exc:
                logger.error(
                    "redis_ttl_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"TTL failed for key={key}") from exc

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------

    async def sadd(self, key: str, *members: str) -> int:
        """Add *members* to the set at *key*. Returns number of new members added."""
        with tracer.start_as_current_span(
            "redis.sadd",
            attributes={
                "db.system": "redis",
                "db.operation": "SADD",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                count: int = await client.sadd(key, *members)
                return count
            except RedisError as exc:
                logger.error(
                    "redis_sadd_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"SADD failed for key={key}") from exc

    async def srem(self, key: str, *members: str) -> int:
        """Remove *members* from the set at *key*. Returns number removed."""
        with tracer.start_as_current_span(
            "redis.srem",
            attributes={
                "db.system": "redis",
                "db.operation": "SREM",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                count: int = await client.srem(key, *members)
                return count
            except RedisError as exc:
                logger.error(
                    "redis_srem_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"SREM failed for key={key}") from exc

    async def smembers(self, key: str) -> set[str]:
        """Return all members of the set at *key*."""
        with tracer.start_as_current_span(
            "redis.smembers",
            attributes={
                "db.system": "redis",
                "db.operation": "SMEMBERS",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                members: set[str] = await client.smembers(key)
                return members
            except RedisError as exc:
                logger.error(
                    "redis_smembers_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"SMEMBERS failed for key={key}") from exc

    async def sismember(self, key: str, member: str) -> bool:
        """Return *True* if *member* is in the set at *key*."""
        with tracer.start_as_current_span(
            "redis.sismember",
            attributes={
                "db.system": "redis",
                "db.operation": "SISMEMBER",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                result: bool | int = await client.sismember(key, member)
                return bool(result)
            except RedisError as exc:
                logger.error(
                    "redis_sismember_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"SISMEMBER failed for key={key}") from exc

    async def scard(self, key: str) -> int:
        """Return the number of members in the set at *key*."""
        with tracer.start_as_current_span(
            "redis.scard",
            attributes={
                "db.system": "redis",
                "db.operation": "SCARD",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                count: int = await client.scard(key)
                return count
            except RedisError as exc:
                logger.error(
                    "redis_scard_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(f"SCARD failed for key={key}") from exc

    # ------------------------------------------------------------------
    # Bulk / pipeline operations
    # ------------------------------------------------------------------

    async def set_with_members(
        self,
        key: str,
        members: set[str],
        ttl: int | None = None,
    ) -> bool:
        """Atomically replace a set: DELETE + SADD + optional EXPIRE in a pipeline.

        This is the primary pattern for refreshing a blacklist or similar cache.
        """
        with tracer.start_as_current_span(
            "redis.set_with_members",
            attributes={
                "db.system": "redis",
                "db.operation": "SET_WITH_MEMBERS",
                "db.redis.key": key,
            },
        ):
            try:
                client = self._require_client()
                async with client.pipeline(transaction=True) as pipe:
                    await pipe.delete(key)
                    if members:
                        await pipe.sadd(key, *members)
                    if ttl is not None:
                        await pipe.expire(key, ttl)
                    await pipe.execute()
                logger.info(
                    "redis_set_with_members",
                    extra={"key": key, "member_count": len(members), "ttl": ttl},
                )
                return True
            except RedisError as exc:
                logger.error(
                    "redis_set_with_members_failed",
                    extra={"key": key, "error": str(exc)},
                )
                raise RedisOperationError(
                    f"SET_WITH_MEMBERS failed for key={key}"
                ) from exc
