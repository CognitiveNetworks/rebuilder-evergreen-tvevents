# ADR 004: Standalone Redis Module for Caching

## Status
Accepted

## Context
The legacy service uses a file-based cache for blacklisted channel data. This approach has multiple problems: the cache is not shared across pods (each pod maintains its own file), the cache is lost on pod restart, and file I/O on ephemeral container storage is fragile. The legacy `cnlib` library bundles a Redis client, but the application does not use it directly for caching.

Other services in the platform also need a reusable Redis client with consistent connection management, retry logic, and health checking. Building Redis caching inline in this service would solve the immediate problem but miss the opportunity for reuse.

## Decision
Create a standalone **`rebuilder-redis-module`** Python package that provides a reusable Redis client with connection pooling, retry logic, and health checks. Use this module in the evergreen-tvevents service for blacklist caching.

## Alternatives Considered
- **Use `redis-py` directly** — Rejected. Directly using `redis-py` in the application would work but would not be reusable across services. Each service would need to independently implement connection management, retry patterns, serialization conventions, and health checks.
- **AWS ElastiCache Memcached** — Rejected. Redis is more versatile than Memcached: it supports TTL per key, data structures (sets, sorted sets), and pub/sub. The additional capabilities justify the similar operational cost.
- **Keep file cache + shared volume** — Rejected. A shared volume (EFS or similar) would add infrastructure complexity and still be slower than Redis. File-based caching is inherently fragile in containerized environments and does not scale horizontally.

## Consequences
- **Shared-nothing pods** — No pod holds local state. Redis is the single source of truth for cached data. Any pod can serve any request with consistent cache state.
- **Cache consistency** — All pods read from and write to the same Redis instance. Cache invalidation is immediate and visible to all pods.
- **Reusable module** — The `rebuilder-redis-module` package can be used by other services in the platform, reducing duplication of Redis connection/retry patterns.
- **Trade-off: infrastructure dependency** — Adds Redis (AWS ElastiCache) as an infrastructure dependency. Requires provisioning, monitoring, and capacity planning for the Redis cluster.
