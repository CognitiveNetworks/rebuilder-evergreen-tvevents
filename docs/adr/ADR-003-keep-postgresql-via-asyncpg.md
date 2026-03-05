# ADR 003: Keep PostgreSQL via asyncpg

## Status
Accepted

## Context
The legacy service uses PostgreSQL (AWS RDS) to store blacklisted channel data. The database driver is `psycopg2` with no connection pooling — each query opens a new connection to RDS and closes it after the query completes. This creates unnecessary connection churn, increases query latency due to TCP/TLS handshake overhead, and risks hitting RDS connection limits under load.

The database schema is simple (a small set of tables for channel blacklist data) and PostgreSQL is well-suited for the workload.

## Decision
**Keep PostgreSQL** (AWS RDS) as the database. Replace `psycopg2` with **`asyncpg`** for async support and built-in connection pooling.

## Alternatives Considered
- **Switch to DynamoDB** — Rejected. PostgreSQL handles the workload well, the schema is simple and relational, and migrating to DynamoDB would add complexity (data migration, new access patterns, eventual consistency handling) without meaningful benefit.
- **Use psycopg3 with async** — Rejected. `psycopg3` supports async via `psycopg[async]`, but `asyncpg` has better benchmark performance for simple query patterns (which is the dominant access pattern in this service) and provides built-in connection pooling without additional configuration.

## Consequences
- **Async queries** — Database calls no longer block the event loop. Combined with FastAPI's async handlers, the service can handle concurrent requests efficiently.
- **Connection pooling** — `asyncpg` maintains a pool of connections to RDS, eliminating per-query connection overhead. Pool size is configurable via environment variables.
- **Reduced RDS connection churn** — Persistent pooled connections reduce load on the RDS instance and avoid TCP/TLS handshake costs on every query.
- **No schema changes required** — The database schema remains unchanged. Only the driver and connection management change.
