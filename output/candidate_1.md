# Rebuild Candidate: Full-Stack Modernization of evergreen-tvevents

## One-Sentence Summary

Replace the cnlib-dependent, Firehose-based Flask TV event collector with a standalone FastAPI service that delivers events to Kafka, caches via a reusable Redis module, and ships with full SRE observability and Terraform IaC.

## Current State

A Python 3.10 Flask service (`tvevents-k8s`) running on AWS EKS collects TV event telemetry from millions of Vizio SmartCast TVs. The service depends on `cntools_py3/cnlib` (a git submodule bundling 80+ transitive dependencies) for three functions: HMAC hash validation, Kinesis Firehose delivery, and logging. Events are validated against HMAC security hashes and event-type schemas, checked against a PostgreSQL blacklist (RDS), obfuscated if needed, and delivered to AWS Kinesis Data Firehose streams. The application has no OpenAPI spec, no SRE diagnostic endpoints, no connection pooling, a fragile file-based cache, and embedded PagerDuty alerting. Production scales to 300–500 pods.

## Target State

A Python 3.12 FastAPI service (`rebuilder-evergreen-tvevents`) with:
- Zero cnlib dependency — standalone HMAC validation using `hmac.compare_digest()`
- Kafka event delivery via `confluent-kafka` replacing Firehose
- Redis-backed blacklist cache via `rebuilder-redis-module` (standalone, reusable package)
- Automatic OpenAPI spec with Pydantic request/response models and examples
- Full `/ops/*` SRE diagnostic and remediation endpoints with Golden Signals
- Async-native with `uvicorn` — no gevent monkey-patching
- ~20–25 targeted dependencies (from 80+)
- Terraform IaC for EKS, Kafka, Redis, RDS access
- Comprehensive unit tests with domain-realistic TV telemetry data

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.12 |
| Framework | FastAPI | Latest stable |
| ASGI Server | Uvicorn | Latest stable |
| Validation | Pydantic v2 | Latest stable |
| Database | PostgreSQL (AWS RDS) | Existing — via `asyncpg` |
| Cache | Redis | via `rebuilder-redis-module` (`redis[hiredis]`) |
| Message Queue | Apache Kafka | via `confluent-kafka` |
| Observability | OpenTelemetry | Latest stable (SDK + auto-instrumentation) |
| Testing | pytest + pytest-asyncio + httpx | Latest stable |
| Linting | ruff | Latest stable |
| Type Checking | mypy (strict) | Latest stable |
| Container | Docker (python:3.12-slim) | Pinned digest |
| IaC | Terraform | Latest stable |
| CI/CD | GitHub Actions | N/A |

## Migration Strategy

### Phase 1: Parallel Development (no traffic)
1. Build `rebuilder-redis-module` as a standalone package with its own tests and CI
2. Build `rebuilder-evergreen-tvevents` with full feature parity:
   - FastAPI routes matching legacy POST `/` behavior on `/v1/events`
   - Standalone HMAC validation (no cnlib)
   - Kafka producer (no Firehose)
   - Redis blacklist cache (no file-based cache)
   - `/ops/*` SRE endpoints
   - Full unit test suite
3. Docker build + Terraform for dev environment

### Phase 2: Parallel Run (shadow traffic)
1. Deploy new service to dev EKS alongside legacy
2. Mirror production traffic: both services receive events, legacy delivers to Firehose, new delivers to Kafka
3. Compare output JSON from Kafka with Firehose records — validate byte-for-byte format compatibility
4. Kafka → S3 bridge writes to same bucket path structure for downstream consumer compatibility

### Phase 3: Cutover
1. Kong routing shifts traffic from legacy to new service (canary → full)
2. Downstream consumers switch from Firehose-sourced S3 to Kafka-sourced S3 (or direct Kafka consumption)
3. Legacy service decommissioned after validation period

## Data Migration

- **No database migration required.** The application is read-only against `public.tvevents_blacklisted_station_channel_map` — the table structure is unchanged.
- **Cache migration:** File-based cache → Redis. No data migration needed — the cache is populated from RDS on startup.
- **Event delivery format:** The flattened JSON output format (`tvevent_timestamp`, `tvevent_eventtype`, `channelid`, etc.) must be preserved exactly. Golden-file tests against captured legacy output validate compatibility.

## What Breaks

- **Firehose delivery stops** — downstream consumers relying on Firehose-delivered S3 data must switch to Kafka-sourced delivery during Phase 2 bridge period
- **cnlib import paths** — any tooling that imports from `cnlib.cnlib.firehose` or `cnlib.cnlib.token_hash` needs updating (but such tooling is outside the rebuild scope)
- **PagerDuty direct integration** — embedded alerting replaced by external monitoring. PagerDuty rules must be configured in the org's monitoring stack.
- **Helm-only deployment** — Terraform replaces Helm for infrastructure management. Existing Helm workflows need migration.

## Phased Scope

### Phase 1 (MVP — 2–3 weeks)
- `rebuilder-redis-module` standalone package with full tests
- `rebuilder-evergreen-tvevents` with all core functionality:
  - FastAPI with Pydantic models
  - Standalone HMAC validation
  - Kafka producer
  - Redis blacklist cache
  - `/ops/*` SRE endpoints
  - Full unit test suite
  - Dockerfile + docker-compose for local dev
  - GitHub Actions CI pipeline (lint, test, build, scan)
  - Terraform scaffolding

### Phase 2 (Production-Ready — 1–2 weeks)
- Load testing at 300–500 pod scale
- Kafka → S3 bridge for downstream compatibility
- Integration tests against real Kafka/RDS/Redis
- Terraform modules for dev/staging/prod environments
- E2E smoke tests

### Phase 3 (Cutover — 1–2 weeks)
- Shadow traffic validation
- Canary rollout via Kong
- Downstream consumer migration
- Legacy service decommission

## Estimated Effort

| Phase | T-shirt | Rationale |
|---|---|---|
| Phase 1 (MVP) | **M** | Small codebase (~1,200 LOC), well-understood patterns (FastAPI+Kafka+Redis), clean build |
| Phase 2 (Production) | **S** | Load testing and bridge setup — mostly configuration, not code |
| Phase 3 (Cutover) | **S** | Traffic routing changes — operational, not development |
| **Total** | **M** | 4–7 weeks total including validation |

## Biggest Risk

**HMAC hash validation reimplementation.** The `cnlib.token_hash.security_hash_match` function is the authentication gate for every TV event. If the standalone reimplementation has any behavioral difference from cnlib's implementation (hash algorithm, salt preprocessing, encoding, comparison logic), millions of TV requests will be rejected. The cnlib submodule is empty in the clone — the exact implementation cannot be read. Mitigation: capture expected input/output triples from the production legacy service and test exhaustively.

## API Design

### Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/events` | Receive TV event payload | HMAC security hash |
| GET | `/health` | Dependency-checking health check | None |
| GET | `/ops/status` | Service status | Internal |
| GET | `/ops/health` | Deep health check | Internal |
| GET | `/ops/metrics` | Golden Signals + RED metrics | Internal |
| GET | `/ops/config` | Runtime configuration (redacted) | Internal |
| GET | `/ops/dependencies` | Dependency status | Internal |
| GET | `/ops/errors` | Recent error summary | Internal |
| POST | `/ops/drain` | Set drain flag | Internal |
| POST | `/ops/cache/flush` | Flush Redis cache | Internal |
| POST | `/ops/circuits` | Circuit breaker control | Internal |
| PUT | `/ops/loglevel` | Change log level | Internal |
| POST | `/ops/scale` | Scale advisory | Internal |

### Design Principles
- FastAPI auto-generates OpenAPI spec
- Every endpoint has a Pydantic `response_model` with `json_schema_extra` examples
- `/v1/` prefix for API versioning
- Error responses return structured JSON with error type and message (not plain text)

## Observability & SRE

- **Golden Signals**: Latency (p50/p95/p99), Traffic (req/s), Errors (error rate), Saturation (queue depth, connection pool utilization)
- **RED Metrics**: Rate, Errors, Duration — per endpoint and per event type
- **SLOs**: 99.9% availability, p99 latency < 200ms, error rate < 0.1%
- **OTEL**: Traces, metrics, structured JSON logs exported via OTLP to OTEL Collector
- **Health checks**: `/health` returns 503 if Kafka, RDS, or Redis unreachable; `/ops/health` returns detailed dependency status
- **Graceful shutdown**: Drain flag → health returns 503 → load balancer stops sending → flush Kafka buffer → close connections → exit

## Auth & RBAC

- **TV authentication**: Standalone HMAC validation using `hmac.compare_digest()` for constant-time comparison. Salt loaded from AWS Secrets Manager (not plain env var).
- **Roles**:
  - TV clients: POST `/v1/events` (public via Kong)
  - Internal tooling: `/ops/*` (internal network only, not exposed via Kong)
  - Admin: `/ops/drain`, `/ops/cache/flush`, `/ops/loglevel` (restricted)
- **Service-to-service auth**: IAM roles for Kafka producer and RDS reader access (scoped, least-privilege)
- **Audit logging**: All `/ops/*` mutations logged with caller identity and timestamp

## Dependency Contracts

| Dependency | Classification | Interface | Contract | Fallback | Tightly Coupled | Integration Tests |
|---|---|---|---|---|---|---|
| AWS RDS PostgreSQL | Outside rebuild boundary | asyncpg (TCP) | Documented — `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map` | Return cached blacklist from Redis; degrade to empty list | No | Verify query returns expected format |
| Apache Kafka | Inside rebuild boundary | confluent-kafka producer | Documented — topic schema = flattened JSON matching legacy Firehose format | Dead-letter topic + local queue with retry | No | Verify message delivery to test topic |
| Redis (rebuilder-redis-module) | Inside rebuild boundary | redis-py async | Documented — module API | Fallback to RDS query (graceful degradation) | No | Verify get/set/TTL behavior |
| Kong API Gateway | Outside rebuild boundary | HTTP reverse proxy | Documented — routes to `/v1/events` | N/A (infrastructure dependency) | No | N/A |
| AWS Secrets Manager | Outside rebuild boundary | AWS SDK / env injection | Documented — `T1_SALT` secret | Fail startup if salt unavailable | No | Verify secret retrieval |

## Rollback Plan

1. **Service rollback**: Kong routing reverts to legacy `tvevents-k8s` service on EKS. Legacy pods remain warm during the entire cutover period.
2. **Data rollback**: Kafka → S3 bridge stops; Firehose delivery on legacy service resumes. No data loss — both paths write to S3.
3. **Infrastructure rollback**: Terraform state allows `terraform destroy` of new infrastructure. Legacy Helm deployment is unaffected.
4. **Cache rollback**: New Redis cache is additive. Legacy file-based cache continues on legacy pods.
5. **Timeline**: Rollback can be executed in < 5 minutes by reverting Kong routing configuration.
