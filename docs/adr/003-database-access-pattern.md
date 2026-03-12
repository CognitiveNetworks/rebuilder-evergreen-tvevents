# ADR 003: Database Access Pattern — Standalone RDS Module

## Status

Accepted

## Context

The legacy evergreen-tvevents service accesses PostgreSQL RDS through `dbhelper.py`, which contains direct psycopg2 calls with manual connection management. The module handles a single read-only query: fetching the blacklist channel ID set used for channel obfuscation. Connection pooling is basic, and there is no instrumentation on database calls.

This inline database code is tightly coupled to the service. The connection management logic, query execution patterns, and health check behavior are not reusable by other services that need similar PostgreSQL access. The legacy assessment identified this as a modernization opportunity — extracting database access into a shared module with proper pooling, instrumentation, and a stable interface.

The project constraints specify that database access should be implemented as a standalone Python module (external pip package), following the same pattern as the Kafka delivery module. The feasibility assessment flagged the async database driver migration (psycopg3) as a Caution item, recommending psycopg2 with `to_thread` wrappers initially, with async driver adoption deferred to Phase 3.

Multiple rebuilt services will need PostgreSQL access with similar requirements: connection pooling, query execution, OTEL instrumentation, and health checks. A standalone module addresses all of these needs once.

## Decision

Extract database access into a standalone RDS Python module, published as an independently versioned pip package. The module will provide:

- Connection pooling (psycopg2 connection pool)
- Query execution with parameterized queries
- OTEL instrumentation via Psycopg2Instrumentor for automatic span generation
- Health check endpoint support (connection validation)
- Configuration via environment variables (host, port, database, credentials)

The initial implementation uses psycopg2 (synchronous driver). The service will call database functions through `asyncio.to_thread` to maintain async endpoint compatibility. Migration to psycopg3's native async driver is deferred to Phase 3, at which point the module's internal implementation changes while the external interface remains stable.

## Alternatives Considered

**Keep inline database code in dbhelper.py.** This minimizes initial migration effort but perpetuates tight coupling. The connection management, query patterns, and health check logic cannot be reused by other services without copy-paste. Instrumentation must be added per-service. Rejected.

**SQLAlchemy ORM.** SQLAlchemy provides a full object-relational mapping layer with connection pooling, session management, and query building. For a service that executes a single read-only query (fetching a list of blacklist IDs), an ORM is substantial overhead. The abstraction layers add complexity without benefit when the query is a simple SELECT. Rejected.

**Async-first with psycopg3 from Phase 1.** psycopg3 provides a native async interface that would eliminate the `to_thread` wrapper. However, the feasibility assessment flagged this as a Caution item: psycopg3 introduces a new driver with different connection pooling semantics, and the service's single simple query does not justify the added Phase 1 complexity. The `to_thread` approach is functionally equivalent for this workload. Rejected.

## Consequences

**Positive:**
- Clean module boundary separates database concerns from service business logic.
- Reusable across multiple rebuilt services that need PostgreSQL access.
- Independent versioning allows the module to evolve (e.g., psycopg3 migration) without requiring simultaneous service releases.
- OTEL instrumentation is built into the module, providing database-layer observability automatically.
- Health check support enables standardized readiness probes across services.

**Negative:**
- An additional pip package must be maintained, versioned, and published.
- The module's interface must be designed to remain stable across the psycopg2 → psycopg3 transition in Phase 3. Interface instability would cascade to all consuming services.
- The `to_thread` wrapper in Phase 1 adds a thin abstraction that consumes a thread pool thread per database call. For the current single-query workload this is negligible, but it would not scale well for high-concurrency database access patterns (addressed by Phase 3 async migration).
