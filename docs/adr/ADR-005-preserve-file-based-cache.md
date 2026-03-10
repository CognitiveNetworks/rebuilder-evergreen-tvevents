# ADR 005: Preserve File-Based Cache (No Redis)

## Status

Accepted

## Context

The legacy tvevents-k8s service caches blacklisted channel IDs in a local file at `/tmp/.blacklisted_channel_ids_cache`. The cache is populated from RDS at pod startup (via entrypoint.sh) and on first request (if file is missing). The in-memory list is loaded from the file cache on first access. This design avoids a network dependency for every request and works reliably at 100-200 pod scale. The user explicitly requires preserving the file-based cache and not migrating to Redis.

## Decision

Preserve the file-based cache at `/tmp/.blacklisted_channel_ids_cache`. Same format (JSON array of channel IDs), same population logic (RDS query at startup, file fallback on first request), same in-memory list for fast lookups. Add a `/ops/cache/flush` endpoint to clear and rebuild the cache on demand.

## Alternatives Considered

- **Redis (AWS ElastiCache)** — Rejected. User explicitly prohibits Redis migration. File cache works correctly and introduces no external dependency. Redis would add network latency, operational complexity, and a new failure mode for a simple lookup pattern.
- **In-memory only (no file persistence)** — Rejected. File persistence survives process restarts within the same pod and allows cache initialization before the ASGI server starts accepting requests (via entrypoint.sh).

## Consequences

- **Positive:** No new infrastructure dependency. No network latency for cache reads. Simple, battle-tested pattern. Preserves existing business logic without re-invention.
- **Negative:** Cache is local to each pod — not shared. Cache updates require either pod restart, `/ops/cache/flush` call, or a new deployment. Stale data window between RDS updates and cache refresh.
- **Mitigation:** `/ops/cache/flush` endpoint enables on-demand cache refresh. Entrypoint initialization ensures fresh cache on every pod start.
