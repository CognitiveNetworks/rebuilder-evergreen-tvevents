# Rebuild Scope

---

## Current Application

### Overview

> tvevents-k8s is a high-throughput TV event ingestion service that receives telemetry data from Vizio smart TVs. It validates incoming payloads (HMAC hash verification, required parameter checks, event-type-specific validation), transforms/flattens the data, obfuscates blacklisted channel information, and delivers the processed events to AWS Kinesis Data Firehose streams for downstream analytics. The service runs at scale (100-200 pods) on AWS EKS. It was built on Python/Flask and is actively maintained with recent OTEL instrumentation and CVE patches.

### Tech Stack

| Layer | Technology | Version | Notes |
|---|---|---|---|
| Frontend | None | | Headless API service |
| Backend | Python / Flask | 3.10 / 3.1.1 | Gunicorn + gevent workers |
| Database | PostgreSQL (AWS RDS) | | Blacklisted channel ID lookups |
| Infrastructure | AWS EKS (Kubernetes) | | 100-200 pods in prod |
| CI/CD | GitHub Actions | | Build, push container to ECR |
| Auth | HMAC MD5 (T1_SALT) | | `cnlib.token_hash` |
| Other | AWS Kinesis Data Firehose, file-based cache | | Event delivery + channel blacklist cache |

### Infrastructure

| Question | Answer |
|---|---|
| Cloud provider(s) | AWS |
| Compute | AWS EKS (Kubernetes) |
| Managed database services | AWS RDS PostgreSQL |
| Managed cache/queue services | AWS Kinesis Data Firehose (4 streams: evergreen, legacy, debug-evergreen, debug-legacy) |
| Containerized? | Yes — Docker |
| Container orchestration | AWS EKS (Kubernetes) |
| IaC tool | Helm charts (in `charts/`) |
| Regions/zones | us-east-1 (primary), eu-west-1 (EU region with SHA-256 auth) |
| Networking | ClusterIP service on port 80 → container port 8000, Kubernetes ingress |

### Architecture

> Flask monolith with a single `POST /` ingestion endpoint and a `GET /status` health check. Request flow:
> 1. TV sends POST with JSON payload containing `TvEvent` and `EventData`
> 2. Service validates required params, HMAC hash, and event-type-specific fields
> 3. Service flattens nested JSON, generates output JSON with event-type-specific handling
> 4. Service checks if channel is blacklisted (file cache → RDS fallback) and obfuscates if needed
> 5. Service delivers output to Firehose streams (parallel, via ThreadPoolExecutor)
>
> Key modules: `routes.py` (HTTP handlers), `utils.py` (validation, transformation, delivery), `dbhelper.py` (RDS + file cache), `event_type.py` (event-type dispatch: ACR_TUNER_DATA, NATIVEAPP_TELEMETRY, PLATFORM_TELEMETRY).

### Known Pain Points

> 1. **cnlib git submodule** — Tight coupling to shared library installed via `setup.py install` during Docker build. Creates deployment friction and version conflicts.
> 2. **Kinesis Data Firehose** — Platform is migrating to Apache Kafka (AWS MSK). Firehose integration via cnlib adds another layer of coupling.
> 3. **No OpenAPI spec** — No typed request/response models, no Swagger UI, no contract testing.
> 4. **No `/ops/*` endpoints** — Missing SRE diagnostic and remediation endpoints required by service bootstrap standards.
> 5. **Insecure HMAC comparison** — Uses `==` instead of `hmac.compare_digest()`.
> 6. **Stale dependencies** — ~15 unused packages (boto v2, google-cloud-monitoring, pymemcache, PyMySQL, pyzmq, redis, fakeredis, etc.).
> 7. **No graceful shutdown** — No drain mechanism, no connection pool cleanup on SIGTERM.
> 8. **No quality gates** — No mypy, no ruff, no coverage enforcement, no dead code detection.

### API Surface

> | Method | Path | Description | Auth |
> |---|---|---|---|
> | POST | `/` | TV event ingestion — validate, transform, deliver to Firehose | HMAC (T1_SALT) |
> | GET | `/status` | Health check — returns "OK" | None |

### Dependencies and Integrations

#### Package Dependencies

> 88 runtime dependencies in `pyproject.toml`. Key ones:
> - `flask>=3.1.1`, `gunicorn==23.0.0`, `gevent==25.5.1` — Web stack
> - `psycopg2-binary==2.9.10` — PostgreSQL client
> - `boto3==1.38.14`, `botocore==1.38.14` — AWS SDK (Firehose)
> - `jsonschema==3.2.0` — PlatformTelemetry payload validation
> - `opentelemetry-*` — Full OTEL SDK + instrumentation suite
> - `cnlib` — Git submodule (firehose, token_hash, log)

#### Outbound Dependencies (services this app calls)

> - **AWS Kinesis Data Firehose** — boto3 SDK via cnlib.firehose. 4 delivery streams.
> - **AWS RDS PostgreSQL** — psycopg2 direct connection. Single query: `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map`.

#### Inbound Consumers (services that call this app)

> - **Vizio Smart TVs** — High-volume POST requests with TV event telemetry.
> - **Kubernetes probes** — Liveness and readiness checks on `GET /status:8000`.

#### Shared Infrastructure

> - **AWS RDS PostgreSQL** — `tvevents_blacklisted_station_channel_map` table potentially shared with other services.
> - **AWS Kinesis Data Firehose** — Delivery streams consumed by downstream data pipeline.

#### Internal Libraries / Shared Repos

> - **cnlib** (`cntools_py3/cnlib`) — Git submodule providing `firehose.Firehose`, `token_hash.security_hash_match`, `token_hash.security_hash_token`, `log.getLogger`. To be eliminated in rebuild.

#### Data Dependencies

> - **Downstream data pipeline** — Firehose delivers to S3 buckets for ETL/analytics.

### Observability & Monitoring

> OpenTelemetry SDK integrated with OTLP HTTP exporters to New Relic:
> - **Tracing:** Manual spans throughout (db.connect, db.query, event type validation, firehose delivery). Flask auto-instrumentation.
> - **Metrics:** OTEL counters (request_counter, db_connection, cache read/write, event validation) and histograms (db_query_duration).
> - **Logs:** OTEL log bridge via `LoggerProvider` + `OTLPLogExporter`.
> - **Missing:** No `/ops/metrics` endpoint, no Golden Signals, no RED method, no SLOs, no error budgets.

### Authentication & Authorization

> HMAC-based. TV sends `tvid` + `h` (hash). Server computes `MD5(tvid + T1_SALT)` and compares. Region-based: MD5 for US, SHA-256 for EU. No RBAC. No service-to-service auth beyond HMAC. T1_SALT injected via Kubernetes secrets.

### Data

> - **RDS table:** `public.tvevents_blacklisted_station_channel_map` with `channel_id` column. Read-only from this service.
> - **File cache:** `/tmp/.blacklisted_channel_ids_cache` — JSON array of blacklisted channel IDs, refreshed from RDS on cache miss or startup.
> - **Event payload:** Nested JSON with `TvEvent` (tvid, client, h, EventType, timestamp) and `EventData` (event-type-specific fields).

### Users

> Vizio smart TVs sending telemetry events. No human users interact with the API directly. Internal operations team monitors via New Relic dashboards.

### Adjacent Repositories

| Repo | Clone Location | Relationship to Primary | Shared State |
|---|---|---|---|
| evergreen-template-repo-python | `adjacent/evergreen-template-repo-python/` | Reference template for operational patterns: Dockerfile, entrypoint.sh, environment-check.sh, pip-compile, Helm charts, OTEL setup | None — pattern reference only |

> **Why is this repo included?**
> The template repo defines the organizational standard for Python service operational files. The rebuild must follow its patterns for Dockerfile structure, entrypoint script, environment variable checking, pip-compile workflow, Helm chart templates, and OTEL configuration. It is the adjacent reference, not a runtime dependency.

---

## Target State

### Target Repository

> `rebuilder-evergreen-tvevents` — New repository for the rebuilt application. The legacy `tvevents-k8s` codebase will not be modified.

### Goals

> 1. Replace Flask with **FastAPI** for typed request/response models, auto-generated OpenAPI spec, and Pydantic validation.
> 2. Replace Kinesis Data Firehose with **Apache Kafka (AWS MSK)** for event delivery.
> 3. Eliminate **cnlib** dependency — replace with inline modules and standalone packages.
> 4. Add full **`/ops/*` diagnostic and remediation endpoints** per service bootstrap standards.
> 5. Use **OTEL auto-instrumentation** (`opentelemetry-instrument`) instead of manual instrumentation.
> 6. Follow **evergreen-template-repo-python** patterns for all operational files.
> 7. Use **pip-compile** workflow for dependency management (`pyproject.toml` → `requirements.txt`).
> 8. Preserve **file-based cache** for blacklisted channel IDs (no Redis).
> 9. Preserve all **business logic** — event validation, transformation, obfuscation.
> 10. Fix **HMAC security** to use `hmac.compare_digest()`.
> 11. Create **standalone RDS and Kafka Python modules** outside the main repo.
> 12. Add **comprehensive tests** covering new FastAPI functionality.
> 13. Add **quality gates**: ruff, mypy, pytest-cov, radon, vulture, pip-audit.

### Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | None | Headless API service |
| Backend | Python 3.10 / FastAPI | User override; typed models, OpenAPI auto-gen, async support |
| Database | PostgreSQL (AWS RDS) | Keep existing; accessed via standalone RDS module |
| CI/CD | GitHub Actions | Align with template repo |
| Auth | HMAC (T1_SALT) with `hmac.compare_digest()` | Fix insecure comparison |
| Other | Apache Kafka (AWS MSK), file-based cache, OTEL auto-instrumentation | Kafka replaces Firehose; cache preserved |

### Target Infrastructure

| Question | Answer |
|---|---|
| Target cloud provider | AWS |
| Target compute | AWS EKS (Kubernetes) |
| Containerization | Docker — following template repo Dockerfile pattern |
| Container orchestration | Kubernetes (EKS) |
| IaC tool | Terraform + Helm charts (following template repo pattern) |
| Target regions | us-east-1 |

### Architecture

> FastAPI monolith with Uvicorn, following template repo patterns. Same ingestion flow as legacy but with typed Pydantic models, OpenAPI spec, and Kafka delivery instead of Firehose. Standalone RDS and Kafka modules provide database and message queue abstractions outside the main service code.

### API Design

> - OpenAPI spec auto-generated by FastAPI
> - Pydantic `response_model` on every endpoint
> - `json_schema_extra` with realistic examples on all models
> - Backward-compatible response shapes for TV client compatibility
> - Endpoints: `POST /`, `GET /status`, `GET /health`, `/ops/*` (11 diagnostic + remediation endpoints)

### Observability & SRE

> - **OTEL auto-instrumentation** via `opentelemetry-instrument` in entrypoint
> - **Structured JSON logging** to stdout via Python `logging`
> - **Golden Signals** (latency, traffic, errors, saturation) exposed at `/ops/metrics`
> - **RED method** (rate, errors, duration p50/p95/p99) exposed at `/ops/metrics`
> - **`/ops/*` endpoints**: status, health, metrics, config, dependencies, errors, drain, cache/flush, circuits, loglevel, scale

### Auth & RBAC

> HMAC-based (T1_SALT) with constant-time comparison (`hmac.compare_digest()`). No RBAC. Region-based hash algorithm (MD5 US, SHA-256 EU). T1_SALT from Kubernetes secrets.

### Dependency Contracts

> - **AWS RDS PostgreSQL** — Read-only access to `tvevents_blacklisted_station_channel_map` via standalone RDS module. Fallback: serve from file cache if RDS unavailable.
> - **Apache Kafka (AWS MSK)** — Produce to configured topics via standalone Kafka module. SASL/SCRAM authentication. Fallback: log and drop (same as current Firehose error handling).
> - **Vizio Smart TVs (inbound)** — Backward-compatible POST payload format. Same query parameters (`tvid`, `client`, `h`, `EventType`, `timestamp`).

### Migration Strategy

> Parallel deployment. New service deployed alongside legacy. Traffic shifted via ingress routing. File cache initialization from same RDS instance. Kafka topics configured to mirror Firehose delivery targets.

### Constraints

> 1. Must preserve file-based cache — no Redis.
> 2. Must not re-invent business logic — port validation/transformation/obfuscation directly.
> 3. Must follow template repo patterns for operational files.
> 4. Must create standalone modules outside the repo for RDS and Kafka.

### Out of Scope

> 1. Redis migration for cache.
> 2. Database schema changes.
> 3. Changes to downstream data pipeline consumers.
> 4. EU region deployment (SHA-256 hash variant) — document but defer.
> 5. DAPR sidecar integration — not used by this service.
