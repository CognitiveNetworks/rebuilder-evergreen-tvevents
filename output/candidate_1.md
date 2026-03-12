# Rebuild Candidate: Full-Service Modernization — evergreen-tvevents

> **Reference document.** This is analysis output from the ideation process. It informs decisions but does not override developer-agent/skill.md.

## One-Sentence Summary

Rebuild evergreen-tvevents from Flask/Gunicorn/Firehose to FastAPI/uvicorn/Kafka with standalone RDS and Kafka modules, OTEL auto-instrumentation, and full test coverage — following template-repo-python patterns exactly.

## Current State

- **Framework:** Python 3.10 / Flask 3.1.1 / Gunicorn + gevent (3 workers, 500 connections)
- **Delivery:** AWS Kinesis Firehose via cnlib.firehose.Firehose — up to 6 delivery streams (evergreen+legacy × normal+debug), parallel sends via ThreadPoolExecutor
- **Data:** PostgreSQL RDS for blacklist lookup, 3-tier cache (memory dict → JSON file → DB query)
- **Auth:** T1_SALT HMAC security hash validation via cnlib.token_hash
- **Observability:** Manual OTEL 1.31.1 setup (48 lines of boilerplate), custom metrics on DB/cache ops
- **API:** 2 endpoints (POST `/`, GET `/status`), no OpenAPI spec, no Pydantic models
- **Tests:** None
- **Pain Points:** No tests, manual OTEL boilerplate, AWS Firehose vendor lock-in, Flask sync-only, no API documentation, fragile cnlib symlink, flat requirements.txt without hash pinning

## Target State

- **Framework:** Python 3.12 / FastAPI / uvicorn — async-ready with lifespan management
- **Delivery:** Apache Kafka via standalone module (external Python package) — replaces all Firehose streams
- **Data:** PostgreSQL RDS via standalone module (external Python package) — connection pooling, OTEL instrumented. File-cache retained exactly as-is.
- **Auth:** T1_SALT preserved — cnlib.token_hash.security_hash_match unchanged
- **Observability:** OTEL auto-instrumentation via FastAPIInstrumentor, Golden Signals, /ops/* SRE endpoints
- **API:** OpenAPI auto-generated, Pydantic request/response models, typed error responses
- **Tests:** Unit + integration tests, 80%+ coverage, domain-realistic test data
- **Structure:** Matches template-repo-python exactly — factory, entry point, environment-check, Dockerfile, Helm charts, pip-compile

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.12 |
| Framework | FastAPI | ≥ 0.115.0 |
| Server | uvicorn | ≥ 0.34.0 |
| Database | PostgreSQL (RDS) | via standalone RDS module (psycopg2 initially) |
| Message Delivery | Apache Kafka | via standalone Kafka module (confluent-kafka or aiokafka) |
| Cache | File-based JSON cache | Custom (ported from legacy) |
| Auth | T1_SALT HMAC | cnlib.token_hash |
| Logging | cnlib.log | Structured JSON |
| Observability | OpenTelemetry | 1.31.1 / 0.52b1 auto-instrumentation |
| Dependency Management | pip-compile | pip-tools ≥ 7.5.0 (scripts/lock.sh) |
| Linting | ruff | Latest |
| Type Checking | mypy | Latest |
| Testing | pytest | ≥ 8.0 with pytest-cov, pytest-asyncio |
| Container | Docker | Python 3.12-bookworm base |
| Orchestration | Kubernetes / Helm | Template-repo-python chart structure |
| Autoscaling | KEDA | 1–500 replicas |

## Migration Strategy

### Step 1: Scaffold the Application
Create the FastAPI application factory following template-repo-python exactly:
- `app/__init__.py` → `create_app()` with asynccontextmanager lifespan
- `app/main.py` → `from app import create_app; app = create_app()`
- `app/routes.py` → FastAPI APIRouter with POST and GET /status
- Dockerfile, entrypoint.sh, environment-check.sh from template patterns
- pyproject.toml with FastAPI, uvicorn, OTEL auto stack
- scripts/lock.sh for pip-compile

### Step 2: Build Standalone Modules
Create two external Python packages:
- **rds-module**: Connection management, pooled connections, query execution, OTEL spans, health check
- **kafka-module**: Producer configuration, topic routing, message serialization, error handling, health check

Both installed as pip dependencies in pyproject.toml.

### Step 3: Port Business Logic
Port from legacy in this order (each with tests):
1. Custom exceptions → `app/exceptions.py`
2. Request validation (required params, timestamp, security hash) → `app/validation.py`
3. Event type classification (abstract base + 3 implementations) → `app/event_type.py`
4. Output JSON generation + payload flattening → `app/output.py`
5. Channel obfuscation (blacklist check + content blocked) → `app/obfuscation.py`
6. Blacklist cache (3-tier: memory → file → RDS via standalone module) → `app/blacklist.py`

### Step 4: Wire Delivery Pipeline
Replace Firehose integration with Kafka module:
- Map Firehose stream names → Kafka topic names
- Port `send_to_valid_firehoses()` → `send_to_valid_topics()` using Kafka module
- Port parallel send pattern (async or threaded)
- Validate output JSON parity between legacy Firehose payloads and new Kafka messages

### Step 5: Observability & SRE Endpoints
- OTEL auto-instrumentation is set up in Step 1
- Add Golden Signals metrics (request duration histogram, error counter, traffic counter)
- Add /ops/* SRE diagnostic endpoints (health, config, dependencies, cache status)
- Port custom DB/cache metrics from legacy

### Step 6: Containerization & Deployment
- Finalize Dockerfile with Python 3.12, HEALTHCHECK, non-root containeruser
- Port Helm charts from template with domain-specific values
- Configure KEDA autoscaling
- environment-check.sh with Kafka/RDS variable groups replacing Firehose groups

## Data Migration

- **Database schema:** No changes. The `public.tvevents_blacklisted_station_channel_map` table is read-only from the application's perspective and stays on the same RDS instance.
- **Cache file:** The JSON file cache at `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` remains in the same format (`json.dump` / `json.load` of channel ID list). No migration needed.
- **Delivery streams → topics:** Kafka topic names replace Firehose stream names. This is configuration, not data migration. Downstream consumers of the Firehose streams must be redirected to Kafka topics — this is outside the application rebuild scope.
- **Environment variables:** Firehose-specific env vars (stream names, SEND_EVERGREEN, SEND_LEGACY) replaced with Kafka-specific env vars (broker URLs, topic names, auth). Mapped in environment-check.sh and Helm values.yaml.

## What Breaks

1. **Firehose delivery stops** — downstream systems consuming from Firehose streams must switch to Kafka topics. This requires coordination with the data platform team.
2. **Environment variables change** — Firehose stream name env vars are replaced with Kafka configuration (brokers, topics, credentials). All deployment configurations (Helm values, Kubernetes secrets) must be updated.
3. **Container runtime changes** — Gunicorn+gevent → uvicorn changes process model. KEDA scaling parameters may need retuning for the new runtime.
4. **cnlib.firehose dependency drops** — any monitoring or alerting tied to Firehose-specific metrics or CloudWatch alarms needs updating.
5. **Docker user changes** — `flaskuser` → `containeruser`. File permissions on mounted volumes must be verified.

## Phased Scope

### Phase 1 (MVP)
- FastAPI scaffold matching template-repo-python
- Standalone RDS module (sync psycopg2 + connection pool)
- Standalone Kafka module (producer with topic routing)
- Port all business logic (validation, event types, output generation, obfuscation, blacklist cache)
- Wire Kafka delivery pipeline
- OTEL auto-instrumentation
- Unit + integration tests (80%+ coverage)
- Dockerfile, entrypoint.sh, environment-check.sh
- Pydantic request/response models with OpenAPI
- pip-compile with hashes
- Ruff linting + mypy type checking

### Phase 2
- /ops/* SRE diagnostic endpoints
- Golden Signals metrics (beyond auto-instrumentation defaults)
- Helm chart modernization from template (HTTPRoute, Dapr, advanced helpers)
- KEDA autoscaling configuration tuning
- CI/CD pipeline (GitHub Actions: lint, test, build, push)
- Skaffold for local development

### Phase 3
- Async DB driver migration (psycopg3 async) in RDS module
- Full native async/await throughout (replace `to_thread` wrappers)
- API versioning evaluation (based on consumer inventory)
- Performance profiling and optimization under production load
- Chaos engineering tests for Kafka/RDS failure scenarios

## Estimated Effort

| Phase | T-Shirt Size | Rationale |
|---|---|---|
| Phase 1 | **L** | Two standalone modules + full business logic port + test suite from scratch. Partially offset by small API surface (2 endpoints) and clear legacy code. |
| Phase 2 | **M** | SRE endpoints + Helm charts + CI/CD. All patterns come from template. |
| Phase 3 | **S** | Incremental improvements on a working system. |

## Biggest Risk

**Kafka parity validation.** The rebuild replaces 6 Firehose delivery streams with Kafka topics. If the output JSON payloads delivered to Kafka do not exactly match what Firehose was delivering, downstream analytics pipelines break silently. Mitigation: capture Firehose output samples as test fixtures, write parity tests that compare legacy output against rebuilt output byte-for-byte, and run shadow traffic through both paths during cutover.

## API Design

- **POST `/`** → receives TV event JSON, validates, processes, delivers to Kafka. Returns 200 on success, 400 on validation failure, 500 on delivery failure.
- **GET `/status`** → returns `{"status": "ok", "version": "<VERSION>"}`.
- **GET `/ops/health`** → deep health check (Kafka connectivity, RDS connectivity, cache freshness).
- **GET `/ops/config`** → non-sensitive runtime configuration.
- **GET `/ops/dependencies`** → status of each external dependency.
- **OpenAPI:** Auto-generated by FastAPI from Pydantic models. All request and response bodies are typed. `json_schema_extra` examples on all models for functional Swagger UI.
- **Versioning:** Deferred to Phase 3 pending consumer inventory. Root path preserved for backward compatibility.

## Observability & SRE

- **Golden Signals:** Request latency (p50/p95/p99 via histogram), error rate (4xx/5xx counters), traffic (request counter by endpoint), saturation (connection pool utilization, event loop lag).
- **Custom Metrics (ported from legacy):** DB_CONNECTION_COUNTER, DB_QUERY_DURATION, CACHE_READ_COUNTER, CACHE_WRITE_COUNTER, KAFKA_SEND_COUNTER (new), KAFKA_SEND_DURATION (new), KAFKA_SEND_ERROR_COUNTER (new).
- **OTEL Auto-Instrumentation:** FastAPIInstrumentor, Psycopg2Instrumentor (or psycopg3), URLLib3Instrumentor. Additional instrumentors as needed from pyproject.toml.
- **SRE Agent Endpoints:**
  - `/ops/health` — deep health (not just liveness)
  - `/ops/config` — runtime configuration dump (no secrets)
  - `/ops/dependencies` — status of RDS, Kafka, cache file
  - `/ops/cache` — cache statistics and freshness
  - `/ops/errors` — recent error summary
- **SLOs:** Defined in SRE agent config. Target: 99.9% success rate on POST `/`, p99 latency < 200ms.

## Auth & RBAC

- **Machine-to-Machine:** T1_SALT HMAC security hash validation on every POST request. No change from legacy. `cnlib.token_hash.security_hash_match` provides the implementation.
- **RBAC:** Not applicable — this is a device-to-service data ingestion endpoint. No human user roles.
- **Service-to-Service:** No additional auth. Kafka and RDS access controlled by infrastructure credentials (Kubernetes Secrets → environment variables).
- **Audit Logging:** Security hash validation failures logged with request metadata (OTEL traces).

## Dependency Contracts

### 1. PostgreSQL RDS (Outbound)
- **Classification:** Outside rebuild boundary (managed service)
- **Interface:** Direct DB (psycopg2 via standalone RDS module)
- **Contract:** Documented — `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map`
- **Fallback:** File cache serves stale data. Application warns but continues operating.
- **Tightly Coupled:** No — accessed through standalone module interface
- **Integration Tests:** Module-level tests with PostgreSQL test container; app-level tests with mock module

### 2. Apache Kafka (Outbound)
- **Classification:** Outside rebuild boundary (managed service, replacing Firehose)
- **Interface:** Kafka producer via standalone Kafka module
- **Contract:** Must be documented as part of rebuild — topic names, message format (JSON), partitioning strategy, auth mechanism
- **Fallback:** Log and count failed deliveries. Return 500 to caller. No silent message loss.
- **Tightly Coupled:** No — accessed through standalone module interface
- **Integration Tests:** Module-level tests with Kafka test container; app-level tests with mock module

### 3. cnlib (Internal Library)
- **Classification:** Inside rebuild boundary (vendored)
- **Interface:** Python import — `cnlib.token_hash.security_hash_match`, `cnlib.log`
- **Contract:** Documented by usage — hash validation takes (salt, params), returns bool; log is a configured logger
- **Fallback:** No fallback — security hash is required for request validation
- **Tightly Coupled:** Yes — but only two modules used (token_hash, log). Firehose module is dropped.
- **Integration Tests:** Unit tests verify security hash validation with known inputs

### 4. Inbound Consumers — SmartCast Devices (Inbound)
- **Classification:** Outside rebuild boundary
- **Interface:** HTTP POST `/` with JSON body
- **Contract:** Undocumented — must document as part of rebuild. Required params: tvid, client, h, EventType, timestamp. Three event type schemas. T1_SALT hash in `h` parameter.
- **Fallback:** N/A (these are the callers)
- **Tightly Coupled:** No — but response shapes must remain backward-compatible
- **Integration Tests:** Contract tests verifying response shapes for success, validation error, and server error cases

### 5. Downstream Analytics (Indirect Outbound)
- **Classification:** Outside rebuild boundary
- **Interface:** Kafka topics (replacing Firehose → S3/Redshift)
- **Contract:** Undocumented — JSON message format must match legacy Firehose payload format exactly
- **Fallback:** Outside application scope — downstream consumers handle their own retry/backfill
- **Tightly Coupled:** No — decoupled via Kafka
- **Integration Tests:** Parity tests comparing Kafka message payloads against captured Firehose output samples

## Rollback Plan

1. **Pre-cutover:** Legacy evergreen-tvevents container image remains deployed and running. New service deployed alongside with separate ingress.
2. **Shadow traffic:** Route a percentage of traffic to the new service while Firehose-based legacy handles 100%. Compare outputs.
3. **Cutover:** Switch ingress to new service. Legacy remains deployed but receives no traffic.
4. **Rollback trigger:** If error rate exceeds 1% or p99 latency exceeds 500ms.
5. **Rollback action:** Switch ingress back to legacy service. No data migration to undo — the blacklist table is read-only and shared. Kafka topic consumers may need to be paused until the issue is resolved.
6. **Post-rollback:** Diagnose failure using OTEL traces and /ops/* endpoints from the new service. Fix and re-attempt cutover.
