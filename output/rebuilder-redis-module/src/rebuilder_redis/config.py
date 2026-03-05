"""Redis client configuration via Pydantic Settings."""

from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    """Configuration for Redis connection.

    Reads from environment variables with REDIS_ prefix.
    """

    model_config = {"env_prefix": "REDIS_"}

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    ssl: bool = False
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    max_connections: int = 50
    decode_responses: bool = True
    retry_on_timeout: bool = True
    health_check_interval: int = 30
