# Feasibility Analysis

## Approach

Evaluating each High/Critical-impact modernization opportunity for effort, risk, dependencies, and rollback.

---

## Opportunity 1: Remove cntools_py3/cnlib Dependency

**Impact:** Critical

**Effort:** S (Small)
- Only 3 functions consumed from cnlib: `firehose.Firehose`, `token_hash.security_hash_match`, `log.getLogger`
- `log.getLogger` → direct replacement with `logging.getLogger` (trivial)
- `token_hash.security_hash_match` → reimplementation with `hmac` + `hashlib` stdlib (small — the hash logic is straightforward HMAC)
- `firehose.Firehose` → replaced by Kafka producer (handled in Opportunity 2)
- The cnlib submodule is empty in the clone, so we're working from the import signatures and test expectations

**Risk:** Medium
- The exact `security_hash_match` implementation is unknown (cnlib is not initialized). If the hash algorithm includes non-standard preprocessing (e.g., MAC address normalization, encoding changes), the reimplementation could reject valid TV requests. Mitigation: test with production-like payloads, capture expected hash/tvid/salt triples.
- Risk of missing a hidden cnlib import elsewhere — grep shows only 3 import sites, confirmed.

**Dependencies:** Unblocks Opportunity 2 (Kafka replaces Firehose) and Opportunity 9 (dependency pruning).

**Rollback:** If the HMAC reimplementation fails in production, the legacy service on EKS remains active behind Kong. Traffic routing reverts at the gateway level.

**Verdict:** ✅ Go

---

## Opportunity 2: Replace Firehose with Kafka

**Impact:** Critical

**Effort:** M (Medium)
- Kafka producer is a well-understood pattern — `confluent-kafka` is a mature library with clear API
- Routing logic simplification: 4 Firehose stream env vars → Kafka topic configuration
- The main complexity is output JSON format compatibility testing against downstream consumers
- Dead-letter topic, retry logic, and delivery callback handling add moderate implementation work

**Risk:** Medium
- Output JSON format is an implicit contract with unknown downstream consumers. Byte-for-byte testing reduces risk but cannot guarantee format compatibility without enumerating all consumers.
- `confluent-kafka` requires `librdkafka` C library — adds a native dependency to the Docker build. Well-documented but adds build complexity.
- Throughput validation at 300–500 pod scale needs load testing before production cutover.

**Dependencies:** Depends on Opportunity 1 (cnlib removal — Firehose delivery lives inside cnlib).

**Rollback:** Parallel run: new Kafka-based service writes to Kafka while legacy Firehose service continues. Roll back by stopping Kafka consumer and reverting Kong routing.

**Verdict:** ✅ Go

---

## Opportunity 3: Extract Standalone Redis Module

**Impact:** High

**Effort:** M (Medium)
- Standalone Python package with connection management, pooling, async support, OTEL instrumentation
- Design requires surveying Redis usage patterns across consuming services
- Separate repo, CI pipeline, versioned releases, and documentation
- Test suite covering connection lifecycle, retry logic, health checks

**Risk:** Low
- Redis client libraries (`redis-py`) are mature and well-understood
- The module is additive — it doesn't change existing functionality, just provides a clean abstraction
- Version coordination risk is manageable with semantic versioning

**Dependencies:** None — can proceed independently. Used by Opportunity 4 (file cache → Redis).

**Rollback:** N/A — new artifact. If the module doesn't work for other services, they can continue using their current Redis client libraries.

**Verdict:** ✅ Go

---

## Opportunity 4: Replace File-Based Cache with Redis

**Impact:** High

**Effort:** S (Small)
- Replace `dbhelper.py` file read/write with Redis get/set via `rebuilder-redis-module`
- Replace in-memory `_blacklisted_channel_ids` with TTL-based Redis cache
- Add async connection pooling for RDS via `asyncpg` (replaces per-request `psycopg2.connect()`)
- Cache invalidation via TTL (e.g., 5-minute refresh)

**Risk:** Low
- Redis failure degrades to RDS fallback — existing behavior (file cache miss → RDS query) becomes Redis cache miss → RDS query
- Adding Redis as a runtime dependency introduces a new infrastructure component, but it replaces a fragile file-based approach

**Dependencies:** Depends on Opportunity 3 (standalone Redis module).

**Rollback:** If Redis is unavailable, application falls back to RDS query (graceful degradation built into the design).

**Verdict:** ✅ Go

---

## Opportunity 5: Upgrade to Python 3.12+

**Impact:** Medium

**Effort:** S (Small)
- Clean rebuild means starting with Python 3.12 from day one — no migration of existing code required
- Any Python 3.10-specific patterns (match statements, etc.) are forward-compatible
- Some dependencies may need version bumps for 3.12 compatibility

**Risk:** Low
- Python 3.12 is well-established LTS with broad library support
- `confluent-kafka`, `redis`, `fastapi`, `asyncpg` all support 3.12

**Dependencies:** None.

**Rollback:** N/A — new codebase. Version is set once.

**Verdict:** ✅ Go

---

## Opportunity 6: Migrate Flask to FastAPI

**Impact:** High

**Effort:** M (Medium)
- Clean rebuild — rewrite routes in FastAPI, not migrate Flask code
- FastAPI provides: native async, automatic OpenAPI spec, Pydantic request/response validation, built-in dependency injection
- Replaces Flask + gevent monkey-patching with native async + uvicorn
- Event type validation logic moves to Pydantic models (natural fit for the existing schema-based validation)

**Risk:** Low
- FastAPI is well-documented and widely adopted
- The application has only 2 endpoints — the migration surface is small
- The validation logic (HMAC, event type schemas) is business logic that ports directly

**Dependencies:** None — independent of other opportunities.

**Rollback:** N/A — clean rebuild. If FastAPI doesn't work, the legacy Flask service remains active.

**Verdict:** ✅ Go

---

## Opportunity 7: Remove Embedded PagerDuty

**Impact:** Medium

**Effort:** S (Small)
- Remove `pygerduty` from dependencies
- Remove any PagerDuty integration code from the application
- Alerting handled externally by OTEL → OTEL Collector → Cloud Monitoring/Prometheus → PagerDuty

**Risk:** Low
- No application code changes required if PagerDuty was only used for incident alerting (not for runtime logic)
- The SRE agent and external monitoring stack handle alerting

**Dependencies:** None.

**Rollback:** If external alerting is not configured, temporarily add PagerDuty notification rules to the OTEL Collector or monitoring stack.

**Verdict:** ✅ Go

---

## Opportunity 8: Add SRE Diagnostic Endpoints

**Impact:** High

**Effort:** M (Medium)
- Implement full `/ops/*` endpoint suite: status, health, metrics, config, dependencies, errors, drain, cache/flush, circuits, loglevel, scale
- `/ops/metrics` requires Golden Signals middleware: request latency (p50/p95/p99), traffic rate, error rate, saturation
- `/ops/health` requires dependency health checking (Kafka connectivity, RDS connectivity, Redis connectivity)
- `/ops/drain` requires graceful shutdown flag integration with health check

**Risk:** Low
- Standard pattern — well-documented in skill.md
- Middleware-based metrics collection is a solved problem with FastAPI

**Dependencies:** Depends on Opportunity 6 (FastAPI — endpoints are FastAPI routes).

**Rollback:** N/A — additive. Legacy service has no `/ops/*` endpoints, so there's nothing to break.

**Verdict:** ✅ Go

---

## Opportunity 9: Prune Dependency Surface

**Impact:** High

**Effort:** S (Small)
- Clean rebuild starts with minimal dependencies — only what's actually used
- Target: ~20–25 runtime dependencies (from 80+)
- Remove: boto, boto3, botocore, s3transfer, pymemcache, PyMySQL, pyzmq, python-consul, pygerduty, google-cloud-monitoring, google-cloud-core, google-api-core, 15+ unused OTEL instrumentors, protobuf 3.x, gevent
- Add: confluent-kafka, redis (async), asyncpg, fastapi, uvicorn, pydantic

**Risk:** Low
- Clean build — no risk of removing something that's actually used
- Each dependency is explicitly imported and testable

**Dependencies:** All other opportunities feed into this — this is the aggregate result.

**Rollback:** N/A — new dependency list.

**Verdict:** ✅ Go

---

## Opportunity 10: Add Terraform IaC

**Impact:** High

**Effort:** M (Medium)
- Define EKS service, Kafka topic, Redis cluster, RDS access, IAM roles in Terraform
- Environment-specific variable files (dev, staging, prod)
- State backend in S3 with DynamoDB locking
- CI pipeline includes `terraform plan` on PR, `terraform apply` on merge

**Risk:** Low
- Terraform for AWS EKS services is well-documented
- Existing Helm charts provide configuration reference for values

**Dependencies:** None — can proceed independently.

**Rollback:** Infrastructure can be managed manually via Helm (as today) if Terraform has issues.

**Verdict:** ✅ Go

---

## Summary

| # | Opportunity | Impact | Effort | Risk | Verdict | Blocks | Blocked By |
|---|---|---|---|---|---|---|---|
| 1 | Remove cnlib | Critical | S | Medium | Go | 2, 9 | — |
| 2 | Replace Firehose → Kafka | Critical | M | Medium | Go | — | 1 |
| 3 | Extract Redis module | High | M | Low | Go | 4 | — |
| 4 | File cache → Redis | High | S | Low | Go | — | 3 |
| 5 | Python 3.12+ | Medium | S | Low | Go | — | — |
| 6 | Flask → FastAPI | High | M | Low | Go | 8 | — |
| 7 | Remove PagerDuty | Medium | S | Low | Go | — | — |
| 8 | SRE /ops/* endpoints | High | M | Low | Go | — | 6 |
| 9 | Prune dependencies | High | S | Low | Go | — | 1, 2, 3 |
| 10 | Terraform IaC | High | M | Low | Go | — | — |

**All opportunities: Go.** No opportunity was rated No-Go. The critical-path chain is: **1 → 2 → 9** (cnlib removal unblocks Kafka, which unblocks dependency pruning). The parallel chain is: **3 → 4** (Redis module unblocks Redis cache). Opportunity 6 (FastAPI) is independent and can proceed in parallel with the cnlib/Kafka chain.

**Recommended execution order:**
1. Opportunities 3, 5, 6 (Redis module, Python 3.12, FastAPI) — independent, start immediately
2. Opportunity 1 (cnlib removal) — reimplement HMAC validation
3. Opportunities 2, 7 (Kafka, remove PagerDuty) — unblocked by cnlib removal
4. Opportunities 4, 8 (Redis cache, SRE endpoints) — unblocked by Redis module + FastAPI
5. Opportunities 9, 10 (dependency pruning, Terraform) — final cleanup
