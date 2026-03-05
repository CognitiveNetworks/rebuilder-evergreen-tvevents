"""Custom exceptions for rebuilder-redis-module."""


class RedisClientError(Exception):
    """Base exception for Redis client errors."""


class RedisConnectionError(RedisClientError):
    """Raised when Redis connection fails."""


class RedisOperationError(RedisClientError):
    """Raised when a Redis operation fails."""


class RedisConfigError(RedisClientError):
    """Raised when Redis configuration is invalid."""
