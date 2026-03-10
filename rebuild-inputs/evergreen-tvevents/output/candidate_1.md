# Rebuild Candidate: Full-Service FastAPI Rebuild with Kafka and Template Alignment

## One-Sentence Summary

Replace the Flask/cnlib/Firehose tvevents-k8s service with a FastAPI/Kafka rebuild following evergreen-template-repo-python patterns, preserving all business logic and the file-based cache.

## Current State

Python 3.10 Flask monolith running on Gunicorn + gevent on AWS EKS (100-200 pods). Receives TV event telemetry via `POST /`, validates HMAC hash and event-type-specific payloads, transforms/flattens data, obfuscates blacklisted channels, and delivers to AWS Kinesis Data Firehose streams. Depends on `cnlib` git submodule for Firehose delivery, HMAC validation, and logging. No OpenAPI spec, no `/ops/*` endpoints, no typed models, no quality gates.

## Target State

FastAPI service on Uvicorn with Pydantic models, auto-generated OpenAPI spec, OTEL auto-instrumentation, Apache Kafka delivery (replacing Firehose), inline HMAC security module (replacing cnlib), full `/ops/*` SRE endpoint suite, file-based blacklist cache (preserved), standalone RDS and Kafka Python modules, comprehensive test coverage, and all operational files aligned with evergreen-template-repo-python patterns.

## Tech Stack

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.10 |
| Web Framework | FastAPI | latest stable |
| ASGI Server | Uvicorn | latest stable |
| Database Client | psycopg2-binary | 2.9.x |
| Message Queue | confluent-kafka | latest stable |
| Observability | OpenTelemetry SDK + auto-instrumentation | 1.x / 0.x |
| Payload Validation | Pydantic v2 (via FastAPI) + jsonschema | |
| Testing | pytest + pytest-asyncio + pytest-cov + httpx | |
| Linting | ruff | latest stable |
| Type Checking | mypy | latest stable |
| Dependency Management | pip-tools (pip-compile) | |
| Container | Docker (python:3.10-bookworm) | |
| Orchestration | AWS EKS (Kubernetes) + Helm | |
| IaC | Terraform | |

## Migration Strategy

1. **Set up quality gates** — Configure ruff, mypy, pytest-cov, pip-audit in `pyproject.toml`
2. **Create standalone modules** — `rebuilder-rds-module` (connection pool, retry, health check) and `rebuilder-kafka-module` (SASL/SCRAM producer, OTEL, health check)
3. **Build FastAPI application** — Port business logic from legacy, define Pydantic models, implement routes with `response_model`
4. **Implement inline security** — Replace cnlib.token_hash with `app/security.py` using `hmac.compare_digest()`
5. **Implement Kafka delivery** — Replace `send_to_valid_firehoses()` with `send_to_valid_topics()` using Kafka module
6. **Add /ops/* endpoints** — Full diagnostic and remediation suite
7. **Configure OTEL auto-instrumentation** — entrypoint.sh with `opentelemetry-instrument`
8. **Align operational files** — Dockerfile, entrypoint.sh, environment-check.sh, Helm charts following template patterns
9. **Write tests** — Unit tests, API tests with httpx/TestClient, coverage enforcement
10. **Parallel deployment** — Deploy alongside legacy, validate, shift traffic

## Data Migration

No data migration required. The service is stateless — it reads from a shared RDS table (read-only) and writes to delivery streams. The file-based cache is ephemeral and regenerated at pod startup.

- **RDS:** Same `tvevents_blacklisted_station_channel_map` table, same read-only query
- **Cache:** Same `/tmp/.blacklisted_channel_ids_cache` file path and format
- **Output format:** Same flattened JSON structure delivered to Kafka topics instead of Firehose streams

## What Breaks

- **Downstream pipeline** must be configured to consume from Kafka topics instead of (or in addition to) Firehose streams. This is the only external coordination required.
- **Helm chart structure** changes — existing Helm deployment values will need remapping to template chart format.
- **Environment variables** change — Firehose-specific vars replaced by Kafka-specific vars. `FLASK_ENV` and `FLASK_APP` removed.

## Phased Scope

### Phase 1 (MVP — 1-2 weeks)
- FastAPI application with all business logic ported from legacy
- Pydantic models for request/response
- Inline HMAC security module
- Kafka delivery (standalone module)
- RDS client (standalone module)
- File-based blacklist cache
- `GET /status`, `GET /health`, `POST /`
- OTEL auto-instrumentation
- Dockerfile, entrypoint.sh, environment-check.sh following template patterns
- Unit and API tests
- Quality gates (ruff, mypy, pytest-cov)
- `.env.example`, `README.md`

### Phase 2 (1 week)
- Full `/ops/*` endpoint suite (11 endpoints)
- Helm charts following template chart templates
- Terraform modules for infrastructure
- pip-compile workflow (`scripts/lock.sh`)
- CI/CD pipeline (GitHub Actions)
- E2E smoke tests

### Phase 3 (Post-deploy)
- SLO definition and error budget configuration
- Monitoring dashboards for Golden Signals
- PagerDuty alerting configuration
- Performance validation at scale (100-200 pods)
- Legacy service decommission after bake period

## Estimated Effort

| Phase | Effort | Breakdown |
|---|---|---|
| Phase 1 (MVP) | **L** | FastAPI port (M), Kafka module (S), RDS module (S), security module (S), tests (M), operational files (M) |
| Phase 2 | **M** | /ops/* endpoints (M), Helm charts (M), Terraform (S), CI/CD (S) |
| Phase 3 | **S** | Configuration and monitoring setup |
| **Total** | **L** | |

## Biggest Risk

**Payload backward compatibility.** TVs send payloads in a specific nested JSON format that the legacy service validates procedurally. If Pydantic models reject valid production payloads (edge cases in field types, missing optional fields, unexpected extra fields), the service will return 422 errors to TVs that cannot be updated. Mitigation: test with production-representative payloads, configure Pydantic with `model_config = ConfigDict(extra="allow")` where needed.

## API Design

| Method | Path | Description | Response Model |
|---|---|---|---|
| POST | `/` | TV event ingestion | `IngestResponse` |
| GET | `/status` | Health check (legacy compat) | `str` ("OK") |
| GET | `/health` | Alias for /status | `str` ("OK") |
| GET | `/ops/status` | Composite health verdict | `OpsStatusResponse` |
| GET | `/ops/health` | Dependency health | `OpsHealthResponse` |
| GET | `/ops/metrics` | Golden Signals + RED | `OpsMetricsResponse` |
| GET | `/ops/config` | Runtime configuration | `OpsConfigResponse` |
| GET | `/ops/dependencies` | Dependency connectivity | `OpsDependenciesResponse` |
| GET | `/ops/errors` | Recent errors | `OpsErrorsResponse` |
| POST | `/ops/drain` | Graceful shutdown | `OpsDrainResponse` |
| POST | `/ops/cache/flush` | Clear blacklist cache | `OpsCacheFlushResponse` |
| GET | `/ops/circuits` | Circuit breaker state | `OpsCircuitsResponse` |
| PUT | `/ops/loglevel` | Runtime log level | `OpsLogLevelResponse` |

All endpoints use Pydantic `response_model` with `json_schema_extra` examples.

## Observability & SRE

- **OTEL auto-instrumentation** via `opentelemetry-instrument` in entrypoint
- **Golden Signals:** latency (request duration histogram), traffic (request rate counter), errors (error rate counter by status code), saturation (in-flight request gauge)
- **RED Method:** rate (requests/sec), errors (error ratio), duration (p50/p95/p99)
- **SLOs:** Availability ≥ 99.9%, p99 latency ≤ 500ms (to be validated)
- **Structured logging:** JSON to stdout with trace correlation (trace_id, span_id)
- **`/ops/*` endpoints:** Full diagnostic and remediation suite as defined above

## Auth & RBAC

- **Authentication:** HMAC-based (T1_SALT) with `hmac.compare_digest()` for constant-time comparison
- **Hash algorithm:** MD5 for US regions, SHA-256 for EU (`eu-west-1`)
- **No RBAC:** Appropriate for headless device ingestion service
- **T1_SALT:** From Kubernetes secrets via environment variable
- **`/ops/*` auth:** No auth (internal cluster access only via ClusterIP service)

## Dependency Contracts

### AWS RDS PostgreSQL (Outbound)
- **Classification:** Outside rebuild boundary
- **Interface:** psycopg2 via standalone RDS module
- **Contract:** `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map` — documented
- **Fallback:** Serve from file cache if RDS unavailable
- **Tightly Coupled:** No — read-only, single query, can be stubbed
- **Integration Tests:** Verify cache-miss-to-RDS fallback, cache initialization at startup

### Apache Kafka / AWS MSK (Outbound)
- **Classification:** Inside rebuild boundary (new dependency replacing Firehose)
- **Interface:** confluent-kafka via standalone Kafka module
- **Contract:** Produce JSON messages to configured topics — documented in module README
- **Fallback:** Log error and continue (same as current Firehose error handling)
- **Tightly Coupled:** No — producer interface is abstracted by standalone module
- **Integration Tests:** Verify topic routing (evergreen/legacy/debug), message format, SASL auth

### Vizio Smart TVs (Inbound)
- **Classification:** Outside rebuild boundary
- **Interface:** HTTP POST with JSON payload
- **Contract:** Undocumented de facto contract — must be documented as part of rebuild (Pydantic models serve as contract)
- **Fallback:** N/A — service must accept valid TV payloads
- **Tightly Coupled:** Yes — payload format cannot change without TV firmware update
- **Integration Tests:** Validate all three event types with production-representative payloads

### Downstream Data Pipeline (Data Dependency)
- **Classification:** Outside rebuild boundary
- **Interface:** Kafka topics (replacing Firehose → S3)
- **Contract:** Same flattened JSON output format — must be backward compatible
- **Fallback:** N/A — downstream consumers must be configured for Kafka
- **Tightly Coupled:** No — output format is the contract, not the delivery mechanism
- **Integration Tests:** Verify output JSON matches legacy Firehose output format

## Rollback Plan

1. Legacy `tvevents-k8s` service remains unmodified and deployed
2. New service deployed alongside legacy with separate ingress routing
3. Traffic shifted incrementally (canary → percentage → full)
4. If issues detected: shift traffic back to legacy service immediately
5. Kafka topics can coexist with Firehose streams during transition
6. Minimum 30-minute bake period after full traffic shift before considering stable
