# Feasibility Analysis

> **Reference document.** This is analysis output from the ideation process. It informs decisions but does not override developer-agent/skill.md.

This document evaluates each modernization opportunity from `output/modernization_opportunities.md` for effort, risk, dependencies, and rollback viability. Opportunities rated No-Go are excluded from rebuild candidates.

---

## Feasibility by Opportunity

### 1. Flask → FastAPI Migration

| Dimension | Assessment |
|---|---|
| Effort | **L** — Requires rewriting the application factory, route definitions, middleware, and error handling. All request handlers change signatures. However, the application has only 2 endpoints, which limits the blast radius. |
| Risk | **Medium** — FastAPI has different middleware semantics and dependency injection. Response shapes must remain backward-compatible for unknown inbound consumers. |
| Dependencies | Blocks: Python 3.12 (#2), uvicorn (#3), OTEL auto-instrumentation (#11), Pydantic models (#24). Must be done first in the framework layer. |
| Rollback | Deploy legacy Flask service from current container image. No data migration involved. Traffic routing switch. |
| **Verdict** | **Go** — Non-negotiable constraint. Well-understood migration path. Small API surface reduces risk. |

### 2. Python 3.10 → 3.12 Upgrade

| Dimension | Assessment |
|---|---|
| Effort | **S** — Base image change in Dockerfile. No application code changes expected. cnlib compatibility to verify. |
| Risk | **Low** — Python 3.12 is backward-compatible with 3.10. The service uses no deprecated features. |
| Dependencies | None — this is a foundation change that enables all others. |
| Rollback | Revert Dockerfile base image. |
| **Verdict** | **Go** — Minimal effort, no risk, enables the rest of the stack. |

### 3. Gunicorn+gevent → uvicorn

| Dimension | Assessment |
|---|---|
| Effort | **S** — Change entrypoint.sh command from gunicorn to uvicorn. Drop gunicorn/gevent dependencies. |
| Risk | **Low** — uvicorn is the standard ASGI server for FastAPI. Template-repo-python already demonstrates the exact configuration. |
| Dependencies | Requires FastAPI migration (#1). |
| Rollback | Revert entrypoint.sh and reinstall gunicorn. |
| **Verdict** | **Go** — Direct consequence of FastAPI migration. Template provides the exact pattern. |

### 4. ThreadPoolExecutor → native async/await

| Dimension | Assessment |
|---|---|
| Effort | **M** — The main I/O workload is Kafka delivery (replacing Firehose). The standalone Kafka module can be designed async-native from the start. Blacklist cache reads (file I/O, DB query) need async wrappers. |
| Risk | **Medium** — async psycopg2 (or psycopg3) is less battle-tested than sync. File I/O can use `asyncio.to_thread`. |
| Dependencies | Requires FastAPI (#1), standalone Kafka module (#5), standalone RDS module (#7). |
| Rollback | Use `asyncio.to_thread()` wrappers around sync calls as an intermediate step. |
| **Verdict** | **Caution** — Design the standalone modules with async interfaces but initially implement with sync internals wrapped in `to_thread`. Avoids blocking the event loop without requiring full async driver migration on day one. |

### 5. Firehose → Kafka Standalone Module

| Dimension | Assessment |
|---|---|
| Effort | **L** — New Python package outside the repo. Must implement: Kafka producer configuration, topic routing (replacing stream name routing), serialization, error handling, health checks. Must support the same parallel-send pattern as the legacy ThreadPoolExecutor approach. |
| Risk | **High** — This is the largest functional change in the rebuild. Parity validation between Firehose JSON output and Kafka message payloads is critical. Kafka configuration (brokers, auth, topics, partitioning) introduces new operational complexity. |
| Dependencies | Blocks business logic port. Does not depend on FastAPI migration — can be developed in parallel as an external module. |
| Rollback | The standalone module is versioned independently. Roll back by pinning the previous version. If Kafka infrastructure fails, no application-level rollback — this is an infrastructure dependency. |
| **Verdict** | **Go** — Non-negotiable constraint. Risk is managed by: (a) standalone module with its own tests, (b) interface abstraction matching the Firehose send pattern, (c) domain-realistic integration tests with Kafka test containers. |

### 6. Delivery Abstraction Layer

| Dimension | Assessment |
|---|---|
| Effort | **M** — Define a `DeliveryBackend` protocol/interface that `send_to_valid_firehoses()` replacement uses. Kafka module implements it. |
| Risk | **Low** — This is a design decision, not a technology risk. |
| Dependencies | Co-developed with Kafka module (#5). |
| Rollback | Inline the Kafka calls directly. |
| **Verdict** | **Go** — Reduces coupling and improves testability. The legacy code already has an implicit delivery interface in `push_changes_to_firehose()`. |

### 7. RDS Standalone Module Extraction

| Dimension | Assessment |
|---|---|
| Effort | **L** — New Python package outside the repo. Must extract: connection management, query execution, OTEL instrumentation. The blacklist cache logic stays in the main app (it's business logic), but the underlying DB access moves to the module. |
| Risk | **Medium** — Must cleanly separate "how to talk to PostgreSQL" (module) from "what to query and how to cache" (app). Interface boundary is clear: module provides `execute_query()` and connection lifecycle; app provides SQL and caching logic. |
| Dependencies | Can be developed in parallel with the Kafka module. Blocks the blacklist cache port. |
| Rollback | Inline psycopg2 calls directly in the app (revert to current pattern). |
| **Verdict** | **Go** — Non-negotiable constraint. Clear separation boundary. Module handles connection pooling, retries, and OTEL spans; app handles domain queries. |

### 8. Async DB Driver (psycopg3/asyncpg)

| Dimension | Assessment |
|---|---|
| Effort | **M** — Replace psycopg2 with psycopg3 async or asyncpg in the standalone RDS module. |
| Risk | **Medium** — psycopg3 async is stable but less widely deployed. asyncpg has different API semantics. |
| Dependencies | Requires RDS standalone module (#7). |
| Rollback | Use psycopg2 with `asyncio.to_thread()` wrapper. |
| **Verdict** | **Caution** — Start with psycopg2 + `to_thread()` in the standalone module. Migrate to async driver in Phase 2 once the module interface is stable. |

### 9. Connection Pooling Formalization

| Dimension | Assessment |
|---|---|
| Effort | **S** — The standalone RDS module should include connection pooling (psycopg2.pool or psycopg3 pool). |
| Risk | **Low** — Well-understood pattern. |
| Dependencies | Part of RDS module (#7). |
| Rollback | Single-connection fallback. |
| **Verdict** | **Go** — Include in the RDS module from the start. |

### 10. Startup Resilience (Graceful Degradation)

| Dimension | Assessment |
|---|---|
| Effort | **S** — Modify `initialize_blacklisted_channel_ids_cache()` to warn instead of RuntimeError when RDS is unreachable and a cache file exists. |
| Risk | **Low** — Strictly additive improvement. Current behavior (fail hard) is always available as fallback. |
| Dependencies | None — can be done at any point during the cache port. |
| Rollback | Revert to `raise RuntimeError`. |
| **Verdict** | **Go** — Simple, high-value resilience improvement. |

### 11. Manual OTEL → Auto-Instrumentation

| Dimension | Assessment |
|---|---|
| Effort | **S** — Replace 48 lines of manual TracerProvider/MeterProvider/LoggerProvider setup with `FastAPIInstrumentor.instrument_app(app)`. Template-repo-python provides the exact pattern. |
| Risk | **Low** — OTEL auto-instrumentation is mature. Template proves the pattern works. |
| Dependencies | Requires FastAPI (#1). |
| Rollback | Re-add manual OTEL setup. |
| **Verdict** | **Go** — Non-negotiable constraint. Dramatic simplification. |

### 12. Golden Signals Instrumentation

| Dimension | Assessment |
|---|---|
| Effort | **M** — Implement request duration histogram (p50/p95/p99), error rate counter, request counter (traffic), and connection pool saturation metrics. |
| Risk | **Low** — Standard OTEL metrics patterns. |
| Dependencies | Requires OTEL auto-instrumentation (#11). Some metrics come free from auto-instrumentation. |
| Rollback | Remove custom metric recording calls. |
| **Verdict** | **Go** — Standard SRE requirement. |

### 13. /ops/* Diagnostic Endpoints

| Dimension | Assessment |
|---|---|
| Effort | **S** — Add a separate APIRouter mounted at `/ops` with health, config, dependencies, errors, and metrics endpoints. |
| Risk | **Low** — Read-only diagnostic endpoints. |
| Dependencies | Requires FastAPI (#1). |
| Rollback | Remove the router. |
| **Verdict** | **Go** — Required by SRE agent pattern. |

### 14. T1_SALT Security Hash Preservation

| Dimension | Assessment |
|---|---|
| Effort | **S** — Port `validate_security_hash()` as-is. cnlib.token_hash.security_hash_match is unchanged. |
| Risk | **Low** — Direct port with no logic changes. |
| Dependencies | cnlib must be available in the rebuilt container. |
| Rollback | N/A — this is a direct port. |
| **Verdict** | **Go** — Non-negotiable. Zero logic change. |

### 15. Dependency Hash Pinning (pip-compile)

| Dimension | Assessment |
|---|---|
| Effort | **S** — Adopt `scripts/lock.sh` from template-repo-python. Define dependencies in `pyproject.toml`. |
| Risk | **Low** — pip-compile is well-established. |
| Dependencies | None. |
| Rollback | Revert to flat requirements.txt. |
| **Verdict** | **Go** — Non-negotiable constraint. Eliminates supply chain risk. |

### 16. Non-Root Container User

| Dimension | Assessment |
|---|---|
| Effort | **S** — Change Dockerfile from `flaskuser` to `containeruser` UID 10000 matching template. |
| Risk | **Low** — Already using non-root in legacy. Name and path change only. |
| Dependencies | None. |
| Rollback | Revert Dockerfile USER directive. |
| **Verdict** | **Go** — Trivial. |

### 17. Test Suite Creation

| Dimension | Assessment |
|---|---|
| Effort | **L** — No existing tests. Must create: unit tests for validation, event types, output generation, obfuscation; integration tests for blacklist cache, Kafka delivery; contract tests for API responses. Target: 80%+ coverage. |
| Risk | **Medium** — Writing tests from scratch for business logic that has never been formally tested may surface undocumented behaviors. |
| Dependencies | Can proceed in parallel with implementation. Kafka/RDS modules need their own test suites. |
| Rollback | N/A — tests are additive. |
| **Verdict** | **Go** — Non-negotiable constraint. Must cover all new functionality. |

### 18. CI/CD Pipeline

| Dimension | Assessment |
|---|---|
| Effort | **M** — GitHub Actions (or equivalent) pipeline: lint, type check, test with coverage gate, Docker build, push. |
| Risk | **Low** — Standard pipeline. |
| Dependencies | Requires tests (#17), linting (#19). |
| Rollback | Disable pipeline. |
| **Verdict** | **Go** — Standard engineering practice. |

### 19. Linting + Formatting (ruff)

| Dimension | Assessment |
|---|---|
| Effort | **S** — Add ruff config to pyproject.toml. One-time format pass. |
| Risk | **Low** — Purely additive. |
| Dependencies | None. |
| Rollback | Remove config. |
| **Verdict** | **Go** — Quick win. |

### 20. Type Checking (mypy)

| Dimension | Assessment |
|---|---|
| Effort | **S** — Add mypy config. Incremental adoption with `--strict` on new code. |
| Risk | **Low** — Opt-in strictness. |
| Dependencies | None. |
| Rollback | Remove config. |
| **Verdict** | **Go** — Low effort, catches bugs early. |

### 21. pip-compile with Hashes

| Dimension | Assessment |
|---|---|
| Effort | **S** — Same as #15. |
| Risk | **Low** |
| Dependencies | None. |
| Rollback | Revert to flat requirements.txt. |
| **Verdict** | **Go** |

### 22. cnlib Vendored Symlink → Direct COPY

| Dimension | Assessment |
|---|---|
| Effort | **S** — Copy cnlib directory directly in Dockerfile instead of relying on symlink. Template-repo-python shows the pattern. |
| Risk | **Low** — Eliminates fragile symlink. |
| Dependencies | None. |
| Rollback | Re-add symlink. |
| **Verdict** | **Go** — Fixes a known fragility. |

### 23. OpenAPI Auto-Generation

| Dimension | Assessment |
|---|---|
| Effort | **S** — Free with FastAPI. Define Pydantic models and FastAPI generates OpenAPI spec automatically. |
| Risk | **Low** — Automatic. |
| Dependencies | Requires FastAPI (#1). |
| Rollback | N/A — inherent to FastAPI. |
| **Verdict** | **Go** — Zero additional effort with FastAPI. |

### 24. Pydantic Request/Response Models

| Dimension | Assessment |
|---|---|
| Effort | **M** — Define models for: incoming event payloads (3 event types), validation error responses, success responses, `/status` response. Replaces manual dict/validate logic. |
| Risk | **Low** — Improves type safety and documentation. |
| Dependencies | Requires FastAPI (#1). |
| Rollback | Revert to dict-based validation. |
| **Verdict** | **Go** — High value for API documentation and validation correctness. |

### 25. API Versioning

| Dimension | Assessment |
|---|---|
| Effort | **S** — Mount the main router at `/v1/` prefix. |
| Risk | **Low** — But requires all consumers to update the path. |
| Dependencies | FastAPI (#1). Understanding of all inbound consumers. |
| Rollback | Mount at root. |
| **Verdict** | **Caution** — Evaluate after confirming the full consumer set. Adding `/v1/` prefix changes the API contract. May need `/` alias during migration. |

### 26–28. Containerization Modernization (Dockerfile, entrypoint.sh, environment-check.sh)

| Dimension | Assessment |
|---|---|
| Effort | **S** each — Template-repo-python provides exact patterns for all three. |
| Risk | **Low** — Direct pattern adoption. environment-check.sh needs domain-specific variable groups added. |
| Dependencies | None — can be done early. |
| Rollback | Revert to legacy files. |
| **Verdict** | **Go** — Non-negotiable constraint. Template provides blueprints. |

### 29. Helm Chart Modernization

| Dimension | Assessment |
|---|---|
| Effort | **M** — Adopt template-repo-python Helm chart structure with helpers (_common.tpl, _container.tpl, _env.tpl, etc.), HTTPRoute, Dapr components, KEDA. Port domain-specific values (Firehose env vars → Kafka env vars, RDS connection, T1_SALT). |
| Risk | **Medium** — Helm template helpers are complex. Must validate that KEDA scaling, resource limits, and secrets mapping work correctly in the new structure. |
| Dependencies | Requires understanding of Kafka infrastructure config. |
| Rollback | Revert to legacy Chart + values.yaml. |
| **Verdict** | **Go** — Template provides full chart skeleton. Domain values need careful porting. |

### 30. Skaffold for Local Dev

| Dimension | Assessment |
|---|---|
| Effort | **S** — Copy skaffold.yaml from template and adapt. |
| Risk | **Low** — Local dev tooling only. |
| Dependencies | Docker + Helm charts ready. |
| Rollback | Remove skaffold.yaml. |
| **Verdict** | **Go** — Nice to have for local dev iteration. |

---

## Summary Table

| # | Opportunity | Effort | Risk | Verdict |
|---|---|---|---|---|
| 1 | Flask → FastAPI | L | Medium | **Go** |
| 2 | Python 3.10 → 3.12 | S | Low | **Go** |
| 3 | Gunicorn+gevent → uvicorn | S | Low | **Go** |
| 4 | ThreadPoolExecutor → async/await | M | Medium | **Caution** |
| 5 | Firehose → Kafka standalone module | L | High | **Go** |
| 6 | Delivery abstraction layer | M | Low | **Go** |
| 7 | RDS standalone module | L | Medium | **Go** |
| 8 | Async DB driver | M | Medium | **Caution** |
| 9 | Connection pooling | S | Low | **Go** |
| 10 | Startup resilience | S | Low | **Go** |
| 11 | Manual → auto OTEL | S | Low | **Go** |
| 12 | Golden Signals | M | Low | **Go** |
| 13 | /ops/* endpoints | S | Low | **Go** |
| 14 | T1_SALT preservation | S | Low | **Go** |
| 15 | pip-compile hashes | S | Low | **Go** |
| 16 | Non-root container user | S | Low | **Go** |
| 17 | Test suite | L | Medium | **Go** |
| 18 | CI/CD pipeline | M | Low | **Go** |
| 19 | Ruff linting | S | Low | **Go** |
| 20 | mypy type checking | S | Low | **Go** |
| 21 | pip-compile (dup of 15) | S | Low | **Go** |
| 22 | cnlib direct COPY | S | Low | **Go** |
| 23 | OpenAPI auto-gen | S | Low | **Go** |
| 24 | Pydantic models | M | Low | **Go** |
| 25 | API versioning | S | Low | **Caution** |
| 26–28 | Containerization | S | Low | **Go** |
| 29 | Helm modernization | M | Medium | **Go** |
| 30 | Skaffold local dev | S | Low | **Go** |

**No-Go items:** None. All opportunities are feasible.

**Caution items (3):**
1. **#4 ThreadPoolExecutor → async** — Start with `to_thread` wrappers; migrate to full async in Phase 2.
2. **#8 Async DB driver** — Use psycopg2 + `to_thread` first; async driver in Phase 2.
3. **#25 API versioning** — Evaluate after consumer inventory is complete. May need root alias.
