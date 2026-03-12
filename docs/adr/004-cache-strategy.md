# ADR 004: Cache Strategy — File-Cache Retention over Redis

## Status

Accepted

## Context

The legacy evergreen-tvevents service implements a 3-tier cache for blacklist channel IDs: an in-memory Python dictionary (fastest), a JSON file on local disk at `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` (warm fallback), and a PostgreSQL RDS query (cold source of truth). On startup and at configured intervals, the service queries RDS for the current blacklist, writes the result to the JSON file, and loads it into the memory dictionary. If RDS is unavailable, the service falls back to the JSON file; if the file is also missing, the memory cache serves stale data until the next successful refresh.

The blacklist dataset is small — a list of channel IDs that require obfuscation before delivery. The dataset fits comfortably in memory and does not grow proportionally with traffic volume. The cache refresh cycle is infrequent relative to request volume, and cache invalidation is driven by a periodic refresh rather than event-driven updates.

This is a non-negotiable project constraint: the file-based cache must be retained as-is. The assessment confirmed this as the correct approach given the dataset characteristics.

## Decision

Retain the file-based JSON cache exactly as implemented in the legacy service. The 3-tier cache hierarchy (memory → JSON file → RDS query) will be preserved in the rebuilt service. No external caching infrastructure (Redis, Memcached, or similar) will be introduced.

The rebuilt implementation will clean up the cache module's code structure (proper typing, testability, error handling) but will not change the caching strategy or introduce new infrastructure dependencies.

## Alternatives Considered

**Redis.** Redis provides a distributed, high-performance cache with TTL support, pub/sub for cache invalidation, and cluster mode for scaling. For this use case — a small, infrequently-changing list of IDs that fits entirely in memory — Redis adds infrastructure complexity (provisioning, monitoring, connection management, failover configuration) with no measurable benefit. The service runs on EKS with KEDA autoscaling; each pod's local file cache is sufficient. Distributed cache invalidation is unnecessary because the RDS query is the single source of truth and all pods refresh independently on the same schedule. Rejected.

**Memcached.** Memcached provides simple key-value caching with automatic eviction. The same over-engineering concern applies: the dataset is small, fits in memory, and does not benefit from a network-accessible cache layer. Memcached also lacks persistence, so it provides no advantage over the existing JSON file fallback. Rejected.

**SQLite local database.** SQLite could replace the JSON file as the local persistent cache, providing query capabilities and ACID transactions. For a cache that stores a single list of IDs (read as a whole set, written as a whole set), SQLite's relational capabilities are unused. The JSON file format is simpler to inspect, debug, and reason about. Rejected.

## Consequences

**Positive:**
- Zero additional infrastructure: no Redis cluster to provision, monitor, or pay for.
- Battle-tested pattern: the 3-tier cache has operated in production under the legacy service's workload without issues.
- No new dependencies: the JSON file cache uses only Python standard library (`json`, `os`).
- Simple failover: if RDS is down, the stale JSON file continues to serve valid (if slightly outdated) blacklist data. The service degrades gracefully.
- Easy to test: cache behavior can be validated by mocking file reads and dictionary lookups without standing up external infrastructure.

**Negative:**
- If the blacklist dataset grows by orders of magnitude (unlikely given the use case), the in-memory dictionary and JSON file approach would need to be revisited.
- No distributed cache invalidation: if the blacklist changes, each pod discovers the change independently on its next refresh cycle. There is a window (up to one refresh interval) where different pods may serve different blacklist versions. For the obfuscation use case, this temporary inconsistency is acceptable.
- The JSON file is local to each pod, so pod restarts require a fresh RDS query (or falling back to a stale file if the volume is persistent). This is the existing behavior and has not caused issues.
