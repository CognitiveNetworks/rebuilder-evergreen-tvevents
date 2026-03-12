# Rebuild Scope

---

## Current Application

### Overview

evergreen-tvevents is a high-throughput telemetry ingestion service that receives TV event data from Vizio SmartCast devices. It validates incoming requests (security hash, required parameters, timestamps), classifies events by type (NativeAppTelemetry, AcrTunerData, PlatformTelemetry), applies channel obfuscation rules using a blacklist cache, and forwards processed payloads to multiple AWS Kinesis Firehose delivery streams. The service is actively maintained and handles production traffic at scale with KEDA autoscaling from 1 to 500 replicas.

### Tech Stack

| Layer | Technology | Version | Notes |
|---|---|---|---|
| Frontend | None | | |
| Backend | Python / Flask | 3.10 / 3.1.1 | Gunicorn + gevent (3 workers, 500 connections) |
| Database | PostgreSQL (RDS) | 5432 | Blacklist channel ID lookups |
| Infrastructure | AWS EKS | | KEDA autoscaling 1–500 replicas |
| CI/CD | GitHub Actions | | Container builds |
| Auth | T1_SALT security hash | | HMAC-based request validation via cnlib |
| Other | AWS Kinesis Firehose (up to 6 streams), 3-tier file cache | | Memory → file → RDS cache for blacklist |

### Infrastructure

| Question | Answer |
|---|---|
| Cloud provider(s) | AWS |
| Compute | EKS (Kubernetes) |
| Managed database services | RDS PostgreSQL |
| Managed cache/queue services | AWS Kinesis Firehose (delivery streams, not queues) |
| Containerized? | Yes — Docker |
| Container orchestration | EKS with KEDA autoscaler |
| IaC tool | Helm charts |
| Regions/zones | us-east-1 (inferred from RDS hostname tvcdb-development.cognet.tv) |
| Networking | VPC with internal load balancer, Kubernetes services |

### Architecture

Single-container Flask microservice behind a Kubernetes ingress. Request flow: HTTP POST → Flask route → request validation (required params, security hash, timestamp) → event type classification → channel obfuscation (3-tier cache lookup) → parallel Firehose submission via ThreadPoolExecutor. The 3-tier blacklist cache (in-memory dict → JSON file at `/tmp/.blacklisted_channel_ids_cache` → RDS query) is initialized at container startup and refreshed periodically. No async processing — all Firehose sends happen synchronously within the request lifecycle using thread parallelism.

### Known Pain Points

1. **Flask + Gunicorn + gevent** — synchronous framework with cooperative multitasking; modern async frameworks (FastAPI + uvicorn) provide better throughput patterns
2. **Python 3.10** — two major versions behind current (3.12); missing performance improvements and language features
3. **AWS Kinesis Firehose coupling** — 6 Firehose stream names hardcoded via environment variables; no abstraction layer for message delivery
4. **ThreadPoolExecutor for parallelism** — blocking thread model for I/O-bound Firehose writes; async would be more efficient
5. **cnlib/cntools_py3 shared library** — vendored as a symlink (`cnlib -> cntools_py3/cnlib`); used for Firehose client, security hash, and logging
6. **No OpenAPI spec** — Flask app has no auto-generated API documentation
7. **Manual OTEL instrumentation** — TracerProvider, MeterProvider, LoggerProvider all manually configured; could use auto-instrumentation
8. **No unit tests discovered in repo** — tests directory exists but test coverage is unclear
9. **Blacklist cache file dependency** — startup fails if RDS is unreachable and cache file doesn't exist (RuntimeError)

### API Surface

Two endpoints, no versioning, no OpenAPI documentation:

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/` | Receive TV event payloads, validate, classify, obfuscate, forward to Firehose | T1_SALT security hash |
| GET | `/status` | Health check returning `{"status": "ok"}` | None |

Requests require: `tvid`, `client`, `h` (security hash), `EventType`, `timestamp`. The security hash is validated using `cnlib.token_hash.security_hash_match` with the T1_SALT environment variable.

### Dependencies and Integrations

#### Package Dependencies

Key runtime dependencies: Flask 3.1.1, Gunicorn 23.0.0, gevent 24.11.1, psycopg2-binary 2.9.10, boto3 1.36.14, opentelemetry-api 1.31.1, opentelemetry-sdk 1.31.1, plus OTEL instrumentors for Flask, psycopg2, botocore, requests, urllib3. cnlib/cntools_py3 vendored internally.

#### Outbound Dependencies (services this app calls)

1. **AWS Kinesis Firehose** — SDK (boto3), up to 6 delivery streams (evergreen + legacy × normal + debug), documented via environment variables
2. **PostgreSQL RDS** — direct DB (psycopg2), blacklist channel ID lookups from `public.tvevents_blacklisted_station_channel_map`, connection params via environment variables
3. **AWS MSK (Kafka)** — referenced in environment-check.sh (`acr_data_msk_vars`), ACR_DATA_MSK_USERNAME/PASSWORD, but not directly used in application code visible in `app/`

#### Inbound Consumers (services that call this app)

Vizio SmartCast TV devices send POST requests to `/` with telemetry payloads. The exact set of consumers beyond TV firmware is unknown — this is a risk finding.

#### Shared Infrastructure

- **RDS PostgreSQL** (`tvcdb-development.cognet.tv`, database `tvevents`) — shared with unknown other services that may read/write the `tvevents_blacklisted_station_channel_map` table
- **Kinesis Firehose streams** — shared delivery infrastructure; downstream consumers of these streams are outside rebuild scope

#### Internal Libraries / Shared Repos

- **cnlib** (via cntools_py3) — provides `cnlib.firehose.Firehose` (Firehose client), `cnlib.token_hash.security_hash_match` (HMAC validation), `cnlib.log` (structured logging). Vendored as a symlink in the repo.

#### Data Dependencies

Kinesis Firehose streams deliver data to downstream analytics/storage systems (S3, Redshift, etc.) — these are outside rebuild scope but represent a critical data pipeline dependency.

### Observability & Monitoring

Full OTEL instrumentation with TracerProvider, MeterProvider, and LoggerProvider. Exports to New Relic via OTEL exporter (OTEL_EXPORTER_OTLP_ENDPOINT). Custom metrics: DB connection counters, query duration histograms, cache read/write counters, Firehose send operations. Flask, psycopg2, botocore, boto3-sqs, requests, and urllib3 auto-instrumented. Request logging middleware logs method, path, and content-length. No formal SLOs/SLAs defined in code.

### Authentication & Authorization

Requests are validated using a T1_SALT-based security hash. The `h` parameter in each request is compared against a hash computed from request parameters using `cnlib.token_hash.security_hash_match`. No user authentication, no RBAC, no OAuth. This is machine-to-machine auth where TV devices share a salt for request signing. ACR MSK credentials (username/password) are stored as environment variables.

### Data

Single table in scope: `public.tvevents_blacklisted_station_channel_map` with at minimum a `channel_id` column (queried via `SELECT DISTINCT channel_id`). Used for channel obfuscation — blacklisted channel IDs have their data redacted before Firehose delivery. Data volume: the table is small enough to cache entirely in memory and as a JSON file. Migration complexity: low — single table, read-only from application perspective.

### Users

Primary users are Vizio SmartCast TV devices that send telemetry events. The service has no human-facing UI. Operational users interact via `/status` health endpoint and Kubernetes management. Traffic patterns: high-throughput, bursty (KEDA scales 1–500 replicas), primarily POST requests with JSON payloads containing TV event data.

### Adjacent Repositories (Optional)

| Repo | Clone Location | Relationship to Primary | Shared State |
|---|---|---|---|
| rebuilder-evergreen-template-repo-python | `adjacent/rebuilder-evergreen-template-repo-python/` | Provides the target-state reference architecture: FastAPI factory pattern, OTEL auto-instrumentation, pip-compile workflow, Helm chart templates, entrypoint/environment-check patterns, Dockerfile structure | None — template only, no shared runtime state |

> **Why is this repo included?**
> The template-repo-python defines the exact patterns the rebuilt service must follow: FastAPI application factory with asynccontextmanager lifespan, uvicorn entry point, OTEL auto-instrumentation via FastAPIInstrumentor, pip-compile workflow (scripts/lock.sh), environment-check.sh structure, Dockerfile layout (Python 3.12-bookworm, non-root containeruser), and Helm chart templates with advanced helpers. It is the architectural blueprint, not a runtime dependency.

---

## Target State

### Target Repository

rebuilder-evergreen-tvevents — a new repository. The legacy codebase (evergreen-tvevents) will not be modified.

### Goals

1. Migrate from Flask/Gunicorn/gevent to FastAPI/uvicorn following template-repo-python patterns exactly
2. Upgrade from Python 3.10 to Python 3.12
3. Replace AWS Kinesis Firehose with Kafka for event delivery
4. Preserve the existing file-based blacklist cache (do NOT move to Redis)
5. Preserve all existing business logic: request validation, event type classification, channel obfuscation, T1_SALT security hash
6. Use OTEL auto-instrumentation instead of manual OTEL setup
7. Create standalone RDS and Kafka Python modules outside the repo (reusable libraries)
8. Follow template-repo-python exactly for: pip-compile workflow, entrypoint.sh, environment-check.sh, tests, OTEL, Helm charts, T1_Salt handling
9. Write comprehensive tests covering new functionality
10. Produce OpenAPI documentation automatically via FastAPI

### Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | None | No UI — telemetry ingestion service |
| Backend | Python 3.12 / FastAPI / uvicorn | Template-repo-python standard; async-native, auto OpenAPI |
| Database | PostgreSQL (RDS) | Existing RDS instance retained for blacklist lookups |
| CI/CD | GitHub Actions | Existing pipeline tool |
| Auth | T1_SALT security hash (cnlib) | Preserved from legacy — non-negotiable business logic |
| Other | Kafka (replacing Firehose), file-based cache (preserved), standalone RDS + Kafka modules |

### Target Infrastructure

| Question | Answer |
|---|---|
| Target cloud provider | AWS |
| Target compute | EKS (Kubernetes) |
| Containerization | Docker (Python 3.12-bookworm base) |
| Container orchestration | EKS with KEDA autoscaler |
| IaC tool | Helm charts (following template-repo-python patterns) |
| Target regions | us-east-1 |

#### Cloud migration (if changing providers)

Not applicable — staying on AWS.

### Architecture

Single-container FastAPI microservice. Same request flow as legacy but with async handlers: HTTP POST → FastAPI route → request validation (required params, security hash, timestamp) → event type classification → channel obfuscation (3-tier cache: memory → file → RDS) → Kafka message production. The Kafka and RDS integrations will be provided by standalone Python modules that can be reused across services.

### API Design

FastAPI auto-generates OpenAPI spec. Same two-endpoint surface as legacy (POST `/`, GET `/status`) plus `/ops/*` SRE diagnostic endpoints. All endpoints get Pydantic request/response models with `json_schema_extra` examples. Backward-compatible response shapes to avoid breaking existing consumers.

### Observability & SRE

OTEL auto-instrumentation via FastAPIInstrumentor (following template-repo-python pattern). Structured JSON logging via cnlib.log. `/ops/*` diagnostic and remediation endpoints per developer-agent standards. Golden Signals and RED metrics via middleware.

### Auth & RBAC

T1_SALT security hash validation preserved from legacy. No changes to auth model — this is machine-to-machine auth. `/ops/*` endpoints follow whatever access control pattern is standard for the platform.

### Dependency Contracts

1. **Kafka** (replacing Firehose) — outside rebuild boundary, standalone Python module provides the interface. Fallback: log and drop on Kafka unavailability (same as Firehose failure behavior).
2. **PostgreSQL RDS** — outside rebuild boundary, standalone Python module provides the interface. Same connection params. Fallback: file cache serves blacklist data if RDS is unreachable.
3. **cnlib** — inside rebuild boundary (vendored). Provides security hash validation and structured logging.
4. **Inbound consumers (TV devices)** — outside rebuild boundary. Risk: unknown full consumer set. Mitigation: backward-compatible POST `/` request/response contract.

### Migration Strategy

Parallel run — deploy rebuilt service alongside legacy, route increasing traffic via Kubernetes ingress weight shifting. Validate Kafka output matches Firehose output for parity before full cutover.

### Constraints

- Must follow template-repo-python patterns exactly (non-negotiable)
- Must keep file-based blacklist cache (do NOT introduce Redis)
- Must not reinvent business logic — preserve validation, classification, obfuscation as-is
- Standalone RDS and Kafka modules must be created outside the main repo
- Do not reference other local rebuilder repos for context

### Out of Scope

- Redis or any new caching infrastructure
- Changes to the RDS schema or blacklist table structure
- Changes to the T1_SALT security hash algorithm
- Downstream Firehose/S3/Redshift pipeline changes
- Admin UI or human-facing interfaces
- Changes to the legacy evergreen-tvevents repo
