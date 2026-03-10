# PRD: tvevents-k8s Rebuild — FastAPI + Kafka

## Background

The tvevents-k8s service is a high-throughput TV event ingestion service that receives telemetry from Vizio smart TVs, validates and transforms payloads, obfuscates blacklisted channel data, and delivers processed events to AWS Kinesis Data Firehose streams. The legacy assessment (Step 1) identified eight modernization opportunities across architecture, security, observability, and operational alignment. The platform is migrating from Kinesis Data Firehose to Apache Kafka (AWS MSK), and the organization is standardizing on FastAPI for new Python services following the `evergreen-template-repo-python` patterns.

## Goals

1. Replace Flask with FastAPI — typed Pydantic models, auto-generated OpenAPI spec, Swagger UI
2. Replace Kinesis Data Firehose with Apache Kafka (AWS MSK) for event delivery
3. Eliminate cnlib git submodule — inline HMAC security with `hmac.compare_digest()`, standard logging
4. Add full `/ops/*` diagnostic and remediation endpoints (11 endpoints)
5. Enable OTEL auto-instrumentation via `opentelemetry-instrument`
6. Align all operational files with evergreen-template-repo-python patterns (Dockerfile, entrypoint.sh, environment-check.sh, pip-compile, Helm charts)
7. Create standalone RDS Python module (`output/rebuilder-rds-module/`)
8. Create standalone Kafka Python module (`output/rebuilder-kafka-module/`)
9. Preserve file-based blacklist cache — no Redis
10. Preserve all business logic — event validation, transformation, obfuscation
11. Add comprehensive quality gates (ruff, mypy, pytest-cov, pip-audit)
12. Write tests covering new FastAPI functionality

## Non-Goals

1. Migrate file-based cache to Redis or any external cache
2. Re-invent business logic — port validation, transformation, and obfuscation directly from legacy
3. Change the TV payload format — backward compatibility is required
4. Modify downstream data pipeline consumers (they must adapt to Kafka independently)
5. Deploy to EU region (SHA-256 hash variant) — document but defer
6. Add DAPR sidecar integration — not used by this service
7. Add RBAC — not needed for headless device ingestion

## Current Behavior

TVs send `POST /` with a nested JSON payload containing `TvEvent` (tvid, client, h, EventType, timestamp) and `EventData` (event-type-specific fields). The service:
1. Validates required parameters
2. Verifies HMAC security hash (`MD5(tvid + T1_SALT)` via cnlib)
3. Validates event-type-specific fields via dispatch pattern (`event_type_map`)
4. Flattens nested JSON into single-level output
5. Checks channel blacklist (file cache → RDS fallback) and obfuscates if needed
6. Delivers output to Firehose streams in parallel (ThreadPoolExecutor)

Health check: `GET /status` returns "OK" (no dependency verification).

## Target Behavior

Same ingestion flow with these changes:
1. FastAPI with Pydantic models for request/response types
2. HMAC verification uses `hmac.compare_digest()` (constant-time)
3. Kafka delivery replaces Firehose delivery (standalone Kafka module)
4. RDS access via standalone RDS module with connection pooling
5. Full `/ops/*` endpoint suite for SRE agent integration
6. OTEL auto-instrumentation (minimal manual spans for business logic)
7. Graceful shutdown with drain mechanism
8. OpenAPI spec auto-generated with realistic examples

## Target Repository

`rebuilder-evergreen-tvevents` — new repository. The legacy `tvevents-k8s` codebase is not modified.

## Technical Approach

### Architecture

FastAPI monolith on Uvicorn, following the `evergreen-template-repo-python` directory structure:

```
src/tvevents/
├── __init__.py
├── config.py          # Environment configuration via pydantic-settings
├── main.py            # FastAPI app factory, lifespan, middleware
├── api/
│   ├── __init__.py
│   ├── routes.py      # POST /, GET /status, GET /health
│   ├── ops.py         # /ops/* endpoints
│   └── models.py      # Pydantic request/response models
├── domain/
│   ├── __init__.py
│   ├── security.py    # HMAC hash validation (replaces cnlib.token_hash)
│   ├── validation.py  # Request validation logic
│   ├── transform.py   # Payload flattening and output generation
│   ├── obfuscation.py # Channel blacklist obfuscation
│   ├── event_types.py # Event type dispatch (ACR_TUNER_DATA, NATIVEAPP_TELEMETRY, PLATFORM_TELEMETRY)
│   └── delivery.py    # Kafka topic delivery (replaces Firehose)
├── infrastructure/
│   ├── __init__.py
│   ├── database.py    # RDS client wrapper (uses standalone RDS module)
│   └── cache.py       # File-based blacklist cache
└── middleware/
    ├── __init__.py
    └── metrics.py     # Request metrics middleware (Golden Signals, RED)
```

### Tech Stack

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.10 |
| Web Framework | FastAPI | latest stable |
| ASGI Server | Uvicorn | latest stable |
| Database Client | psycopg2-binary | 2.9.x |
| Message Queue Client | confluent-kafka | latest stable |
| Observability | OpenTelemetry SDK + auto-instrumentation | 1.x |
| Payload Validation | Pydantic v2 + jsonschema | |
| Testing | pytest, pytest-asyncio, httpx, pytest-cov | |
| Linting/Formatting | ruff | latest stable |
| Type Checking | mypy | latest stable |
| Dependency Management | pip-tools (pip-compile) | |
| Container | Docker (python:3.10-bookworm) | |
| Orchestration | AWS EKS (Kubernetes) + Helm | |
| IaC | Terraform | |

## API Design

All endpoints use Pydantic `response_model` with `json_schema_extra` examples.

### Core Endpoints

| Method | Path | Description | Response Model |
|---|---|---|---|
| POST | `/` | TV event ingestion — validate, transform, deliver to Kafka | `IngestResponse` |
| GET | `/status` | Health check (legacy compat) — returns "OK" | `str` |
| GET | `/health` | Alias for /status | `str` |

### /ops/* Diagnostic Endpoints

| Method | Path | Description | Response Model |
|---|---|---|---|
| GET | `/ops/status` | Composite health: healthy/degraded/unhealthy | `OpsStatusResponse` |
| GET | `/ops/health` | Dependency-aware health (RDS, Kafka) | `OpsHealthResponse` |
| GET | `/ops/metrics` | Golden Signals + RED metrics | `OpsMetricsResponse` |
| GET | `/ops/config` | Runtime configuration (redacted secrets) | `OpsConfigResponse` |
| GET | `/ops/dependencies` | Dependency connectivity status | `OpsDependenciesResponse` |
| GET | `/ops/errors` | Recent error summary | `OpsErrorsResponse` |

### /ops/* Remediation Endpoints

| Method | Path | Description | Response Model |
|---|---|---|---|
| POST | `/ops/drain` | Set drain flag → health returns 503 | `OpsDrainResponse` |
| POST | `/ops/cache/flush` | Clear blacklist cache, reload from RDS | `OpsCacheFlushResponse` |
| GET | `/ops/circuits` | Circuit breaker state (RDS, Kafka) | `OpsCircuitsResponse` |
| PUT | `/ops/loglevel` | Change runtime log level | `OpsLogLevelResponse` |
| POST | `/ops/scale` | Not applicable (Kubernetes HPA) | `OpsScaleResponse` |

## Observability & SRE

- **OTEL auto-instrumentation** via `opentelemetry-instrument` in entrypoint.sh
- **Golden Signals:** latency (request duration histogram p50/p95/p99), traffic (request rate), errors (error rate by status code), saturation (in-flight requests)
- **RED Method:** rate (requests/sec), errors (error ratio), duration (p50/p95/p99)
- **SLOs:** Availability ≥ 99.9%, p99 latency ≤ 500ms
- **Structured logging:** JSON to stdout with trace correlation (`trace_id`, `span_id`)
- **`/ops/*` endpoints:** Full diagnostic and remediation suite
- **Embedded monitoring removal:** No PagerDuty SDK, Stackdriver, or vendor-specific monitoring clients in application code. Alerting is an infrastructure concern handled by the SRE agent and platform monitoring stack.

## Auth & RBAC

- **Authentication:** HMAC-based (`T1_SALT`) with `hmac.compare_digest()` for constant-time comparison
- **Hash algorithm:** MD5 for US regions, SHA-256 for EU (`eu-west-1`)
- **No RBAC:** Headless device ingestion service — no user roles
- **T1_SALT:** From Kubernetes secrets via environment variable
- **`/ops/*` auth:** No auth (internal cluster access only via ClusterIP)

## External Dependencies & Contracts

### AWS RDS PostgreSQL (Outbound)
- **Type:** Managed service
- **Direction:** Outbound
- **Interface:** psycopg2 via standalone RDS module
- **Contract:** `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map` — documented
- **Inside/outside rebuild:** Outside — same RDS instance
- **Fallback:** Serve from file cache if RDS unavailable
- **SLA expectation:** 99.95% availability (AWS RDS SLA)
- **Integration tests:** Cache-miss-to-RDS fallback, cache initialization at startup

### Apache Kafka / AWS MSK (Outbound)
- **Type:** Managed service (new — replaces Firehose)
- **Direction:** Outbound
- **Interface:** confluent-kafka via standalone Kafka module, SASL/SCRAM auth
- **Contract:** Produce JSON messages to configured topics — documented in module README
- **Inside/outside rebuild:** Inside rebuild boundary (new dependency)
- **Fallback:** Log error and continue
- **SLA expectation:** 99.9% availability (AWS MSK SLA)
- **Integration tests:** Topic routing, message format, SASL auth

### Vizio Smart TVs (Inbound)
- **Type:** Device fleet
- **Direction:** Inbound
- **Interface:** HTTP POST with JSON payload
- **Contract:** De facto contract documented via Pydantic models in rebuild
- **Inside/outside rebuild:** Outside — firmware cannot change
- **Fallback:** N/A — must accept valid payloads
- **SLA expectation:** N/A — devices are the client
- **Integration tests:** All three event types with production-representative payloads

### Downstream Data Pipeline (Data Dependency)
- **Type:** Internal service
- **Direction:** Outbound (data)
- **Interface:** Kafka topics (replacing Firehose → S3)
- **Contract:** Same flattened JSON output format — backward compatible
- **Inside/outside rebuild:** Outside
- **Fallback:** N/A
- **SLA expectation:** N/A — downstream responsibility
- **Integration tests:** Output JSON format matches legacy Firehose output

## Data Migration Plan

No data migration required. The service is stateless:
- **RDS:** Same table, same read-only query, same instance
- **File cache:** Ephemeral, regenerated at pod startup
- **Output format:** Same flattened JSON, delivered to Kafka instead of Firehose

## Rollout Plan

1. Deploy rebuilt service alongside legacy on EKS with separate ingress
2. Validate with synthetic traffic matching production payloads
3. Canary: route 1% of traffic to new service, monitor error rates
4. Incremental: 10% → 25% → 50% → 100% with monitoring at each step
5. Bake period: minimum 30 minutes at 100% before considering stable
6. Rollback: shift traffic back to legacy immediately if issues detected

## Success Criteria

1. All three event types (ACR_TUNER_DATA, NATIVEAPP_TELEMETRY, PLATFORM_TELEMETRY) process correctly
2. Output JSON format is identical to legacy Firehose output
3. HMAC validation produces same accept/reject decisions as legacy
4. Channel obfuscation behavior is identical to legacy
5. `/ops/status` returns healthy when all dependencies are reachable
6. `/ops/status` returns unhealthy/degraded when dependencies are down
7. All quality gates pass (ruff, mypy, pytest, coverage, pip-audit)
8. p99 latency ≤ 500ms under production load
9. Error rate ≤ 0.1% under production load
10. OpenAPI spec is complete and Swagger UI is functional

## ADRs Required

1. ADR-001: Use FastAPI as web framework (replacing Flask)
2. ADR-002: Use Apache Kafka (AWS MSK) for event delivery (replacing Firehose)
3. ADR-003: Keep PostgreSQL via psycopg2 (no ORM, standalone RDS module)
4. ADR-004: Use OTEL auto-instrumentation
5. ADR-005: Preserve file-based cache (no Redis)
6. ADR-006: Inline HMAC security module (replacing cnlib.token_hash)
7. ADR-007: Follow evergreen-template-repo-python operational patterns
8. ADR-008: Create standalone RDS and Kafka Python modules

## Open Questions

1. Kafka topic naming convention — what are the target topic names for evergreen/legacy/debug streams?
2. SASL/SCRAM credentials — where are Kafka credentials stored (AWS Secrets Manager key path)?
3. Connection pool sizing for RDS at 100-200 pod scale — what's the max connections per pod?
4. Downstream pipeline readiness — when will Kafka consumers be configured?
