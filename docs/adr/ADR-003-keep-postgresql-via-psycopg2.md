# ADR 003: Keep PostgreSQL via psycopg2 (No ORM, Standalone RDS Module)

## Status

Accepted

## Context

The legacy tvevents-k8s service connects to AWS RDS PostgreSQL via `psycopg2` for a single read-only query: fetching blacklisted channel IDs from `public.tvevents_blacklisted_station_channel_map`. The database access is embedded in `app/dbhelper.py` with no connection pooling, no retry logic with backoff, and manual OTEL span creation. The user requires a standalone RDS Python module outside the main repo.

## Decision

Keep PostgreSQL (AWS RDS) as the database via `psycopg2-binary`. Create a standalone `rebuilder-rds-module` package with connection pooling, retry logic with exponential backoff and jitter, OTEL instrumentation, and health check. No ORM — the single query does not justify ORM overhead. The application's `database.py` wraps the RDS module for the specific blacklist query.

## Alternatives Considered

- **SQLAlchemy ORM** — Rejected. The service executes a single `SELECT DISTINCT channel_id` query. An ORM adds complexity without benefit for this use case.
- **asyncpg (async)** — Rejected. The service's database access is infrequent (cache initialization + cache-miss fallback). Async is unnecessary for this access pattern and adds complexity.
- **Embed database logic in the service** — Rejected. User explicitly requires a standalone RDS module for reusability across services.

## Consequences

- **Positive:** Simple, direct database access. Standalone module adds connection pooling and retry that the legacy code lacks. No ORM learning curve or overhead.
- **Negative:** psycopg2 is synchronous — would need migration to asyncpg if async becomes required. Connection pool sizing must be validated at 100-200 pod scale.
- **Mitigation:** Connection pool max size configurable via environment variable. RDS module provides health check for `/ops/dependencies` integration.
