# rebuilder-redis-module

Standalone async Redis client library for Vizio rebuilder services. Provides connection pooling, OpenTelemetry tracing, structured logging, and Pydantic v2 configuration.

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import asyncio
from rebuilder_redis import RedisClient, RedisSettings

async def main() -> None:
    settings = RedisSettings(host="localhost", port=6379)

    async with RedisClient(settings) as client:
        # Key-value operations
        await client.set("device:AB:CD:EF:01:23:45", "active", ttl=3600)
        value = await client.get("device:AB:CD:EF:01:23:45")
        print(value)  # "active"

        # Check existence
        if await client.exists("device:AB:CD:EF:01:23:45"):
            print("Device key exists")

asyncio.run(main())
```

## Set Operations (Blacklist Cache)

```python
async with RedisClient(RedisSettings()) as client:
    # Add MAC addresses to a blacklist set
    await client.sadd(
        "blacklist:mac",
        "AA:BB:CC:DD:EE:01",
        "AA:BB:CC:DD:EE:02",
    )

    # Check membership
    is_blocked = await client.sismember("blacklist:mac", "AA:BB:CC:DD:EE:01")

    # Atomic replace — swap the entire blacklist in one pipeline
    new_blacklist = {"11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"}
    await client.set_with_members("blacklist:mac", new_blacklist, ttl=300)

    # Get all members
    members = await client.smembers("blacklist:mac")
```

## Configuration

All settings are read from environment variables with the `REDIS_` prefix via Pydantic Settings:

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database index |
| `REDIS_PASSWORD` | `None` | Authentication password |
| `REDIS_SSL` | `false` | Enable TLS connections |
| `REDIS_SOCKET_TIMEOUT` | `5.0` | Socket read/write timeout (seconds) |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `5.0` | Socket connect timeout (seconds) |
| `REDIS_MAX_CONNECTIONS` | `50` | Connection pool size |
| `REDIS_DECODE_RESPONSES` | `true` | Decode bytes to str |
| `REDIS_RETRY_ON_TIMEOUT` | `true` | Retry on socket timeout |
| `REDIS_HEALTH_CHECK_INTERVAL` | `30` | Seconds between pool health checks |

See [.env.example](.env.example) for a template.

## Observability

Every Redis operation creates an OpenTelemetry span with semantic attributes:

- `db.system` = `"redis"`
- `db.operation` = the Redis command (e.g., `GET`, `SADD`, `SET_WITH_MEMBERS`)
- `db.redis.key` = the key being operated on

Structured log messages use keys like `redis_connected`, `redis_set_with_members`, and `redis_get_failed` for easy filtering.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

Tests use `fakeredis[lua]` as an in-memory Redis backend — no running Redis server required.

## API Reference

### `RedisClient(settings: RedisSettings)`

| Method | Returns | Description |
|---|---|---|
| `connect()` | `None` | Create pool and verify with PING |
| `close()` | `None` | Close pool gracefully |
| `health_check()` | `bool` | PING → True/False |
| `get(key)` | `str \| None` | GET |
| `set(key, value, ttl=None)` | `bool` | SET with optional EX |
| `delete(key)` | `int` | DEL → count removed |
| `exists(key)` | `bool` | EXISTS |
| `expire(key, ttl)` | `bool` | EXPIRE |
| `ttl(key)` | `int` | TTL in seconds |
| `sadd(key, *members)` | `int` | SADD → count added |
| `srem(key, *members)` | `int` | SREM → count removed |
| `smembers(key)` | `set[str]` | SMEMBERS |
| `sismember(key, member)` | `bool` | SISMEMBER |
| `scard(key)` | `int` | SCARD |
| `set_with_members(key, members, ttl=None)` | `bool` | Atomic DEL+SADD+EXPIRE pipeline |
