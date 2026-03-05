# Rebuild Scope

---

## Current Application

### Overview

The **evergreen-tvevents** application (also called `tvevents-k8s`) is a Flask-based Python service that collects TV event telemetry data from Vizio SmartCast TVs. It receives POST requests containing TV event payloads (ACR tuner data, platform telemetry, native app telemetry), validates payloads against security hashes and schema rules, checks for blacklisted channels via a PostgreSQL (RDS) lookup, obfuscates restricted content, and forwards the processed events to AWS Kinesis Data Firehose streams for downstream analytics. The application runs on Kubernetes (EKS) behind Kong API gateway and scales from 1 pod (dev) to 300–500 pods (production). It was built by the Inscape Data Engineering team and is actively maintained. It is a critical data pipeline component in the Inscape Evergreen platform.

### Tech Stack

| Layer | Technology | Version | Notes |
|---|---|---|---|
| Frontend | None | | API-only service |
| Backend | Python / Flask | 3.10 / 3.1.1 | Gunicorn with gevent workers |
| Database | PostgreSQL (AWS RDS) | Unknown | Stores blacklisted channel mappings |
| Infrastructure | AWS EKS (Kubernetes) | Unknown | Helm charts for deployment |
| CI/CD | GitHub Actions | N/A | Black, pytest, pylint, mypy, complexipy, Docker build |
| Auth | HMAC security hash (T1_SALT) | N/A | TVs send hashed tvid for verification |
| Other | AWS Kinesis Data Firehose, Redis (cnlib), memcached (cnlib dependency), ZeroMQ (cnlib dependency), OpenTelemetry, New Relic | Various | Firehose is the primary data sink |

### Infrastructure

| Question | Answer |
|---|---|
| Cloud provider(s) | AWS |
| Compute | AWS EKS (Kubernetes) |
| Managed database services | AWS RDS PostgreSQL |
| Managed cache/queue services | AWS Kinesis Data Firehose (data delivery), no application-level cache service |
| Containerized? | Yes — Docker |
| Container orchestration | Kubernetes (EKS) via Helm |
| IaC tool | Helm charts (no Terraform) |
| Regions/zones | AWS (region configured via AWS_REGION env var) |
| Networking | Kong API Gateway in front, ClusterIP service on port 80 → container port 8000 |

### Architecture

The application is a **single Flask service** deployed as containerized pods on AWS EKS. Architecture:

1. **Ingress**: Kong API Gateway routes TV event POST requests to the service
2. **Flask Routes**: A single POST endpoint (`/`) receives JSON payloads with TV event data; a GET `/status` endpoint for health checks
3. **Validation Layer** (`utils.py`): Validates required parameters, security hash (via cnlib `token_hash`), event-type-specific payload schemas
4. **Event Type Processing** (`event_type.py`): Polymorphic event type classes (`AcrTunerDataEventType`, `PlatformTelemetryEventType`, `NativeAppTelemetryEventType`) validate and transform event data
5. **Blacklist Check** (`dbhelper.py`): Queries PostgreSQL RDS for blacklisted channel IDs, caches results to a local file
6. **Channel Obfuscation** (`utils.py`): If a channel is blacklisted or content is blocked, channel/program data is replaced with "OBFUSCATED"
7. **Firehose Delivery** (`utils.py` via cnlib `firehose`): Processed events are sent in parallel to configured Kinesis Data Firehose streams (evergreen and/or legacy)

Data flows: TV → Kong → Flask POST → validate → transform → blacklist check → obfuscate if needed → Firehose → S3/data lake

### Known Pain Points

1. **cntools_py3/cnlib dependency**: Tightly coupled git submodule dependency for firehose delivery (`firehose.Firehose`) and security hash validation (`token_hash.security_hash_match`). The submodule is frequently out of sync, breaks CI when not initialized, and bundles Redis, memcached, ZeroMQ, and other libraries the app doesn't need.
2. **AWS Kinesis Firehose lock-in**: Data delivery is hardcoded to AWS Kinesis Data Firehose via cnlib. No abstraction layer. Moving to Kafka (which the org is migrating to) requires rewriting the delivery layer.
3. **No Redis abstraction**: The app uses cnlib's Redis wrapper. There is no standalone Redis module that can be used independently.
4. **File-based caching**: Blacklisted channel IDs are cached to a local file (`/tmp/.blacklisted_channel_ids_cache`), which is fragile and not shared across pods.
5. **Python 3.10**: Behind current LTS (3.12+).
6. **Flask instead of async framework**: gevent monkey-patching for concurrency instead of native async.
7. **No OpenAPI spec**: Endpoints are not documented via OpenAPI/Swagger.
8. **Legacy Firehose routing**: Complex env-var-driven routing to multiple firehose streams (evergreen, legacy, debug variants).
9. **Inline OTEL setup**: OpenTelemetry instrumentation is manually configured in `__init__.py` rather than using standard patterns.
10. **Embedded PagerDuty**: `pygerduty` dependency for alerting embedded in the application.
11. **No SRE diagnostic endpoints**: Only `/status` returning "OK" — no `/ops/*` endpoints.
12. **Large dependency surface**: 80+ runtime dependencies including many unused OTEL instrumentors.

### API Surface

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/` | Receive TV event payload, validate, transform, deliver to Firehose | HMAC security hash (T1_SALT) |
| GET | `/status` | Health check — returns "OK" | None |

- No OpenAPI specification
- No versioning
- Single consumer model: TVs post events via Kong API Gateway
- Internal consumers unknown (possibly monitoring/debugging tools)

### Dependencies and Integrations

#### Package Dependencies

Key runtime dependencies: Flask 3.1.1, gunicorn 23.0.0, gevent 25.5.1, redis 6.0.0, psycopg2-binary 2.9.10, boto3 1.38.14, pyzmq 26.4.0, pygerduty 0.38.3, python-consul 1.1.0, pymemcache 4.0.0, PyMySQL 1.1.1, 20+ OpenTelemetry packages, jsonschema 3.2.0, protobuf 3.20.3

#### Outbound Dependencies (services this app calls)

| Service | Interface | Documented |
|---|---|---|
| AWS Kinesis Data Firehose | AWS SDK (boto3 via cnlib) | Partially — env var config |
| AWS RDS PostgreSQL | psycopg2 direct connection | Partially — env var config |

#### Inbound Consumers (services that call this app)

- Vizio SmartCast TVs (via Kong API Gateway) — primary consumer
- Health check probes (Kubernetes liveness/readiness) — `/status`
- Unknown other internal consumers — risk finding

#### Shared Infrastructure

- AWS RDS PostgreSQL `tvevents` database — shared with unknown other services (blacklisted channel map table)

#### Internal Libraries / Shared Repos

| Library | Repo | Usage |
|---|---|---|
| cnlib (cntools_py3) | git@github.com:CognitiveNetworks/cntools_py3.git | `firehose.Firehose` for Kinesis delivery, `token_hash.security_hash_match` for HMAC validation, `log.getLogger` for logging |

#### Data Dependencies

- Downstream: Kinesis Firehose delivers to S3 data lake (`cn-tvevents/<ZOO>/tvevents/` bucket)
- Data warehouse/analytics pipelines consume from S3 (details unknown, outside rebuild scope)

### Observability & Monitoring

- **OpenTelemetry**: Traces, metrics, and logs exported via OTLP HTTP to New Relic
- **Metrics**: Custom OTEL counters for DB connections, queries, cache reads/writes, firehose sends, payload validation, heartbeats
- **PagerDuty**: `pygerduty` dependency (service ID: PSV1WEB) — embedded alerting
- **Health check**: `/status` returns "OK" (no dependency checking)
- **No SLOs/SLAs defined**
- **No structured SRE endpoints**

### Authentication & Authorization

- **TV authentication**: HMAC-based security hash — TVs send a hash (`h`) derived from `tvid` and a shared salt (`T1_SALT`). The app calls `cnlib.token_hash.security_hash_match()` to verify.
- **No RBAC**: All-or-nothing — if you have the salt, you can post events.
- **No service-to-service auth**: No IAM-scoped auth between app and Firehose/RDS beyond AWS credentials.
- **Hardcoded salt env var**: `T1_SALT` loaded from environment.

### Data

- **PostgreSQL table**: `public.tvevents_blacklisted_station_channel_map` — maps `channel_id` values that should be obfuscated
- **No database writes**: Application only reads from RDS
- **Data volume**: High throughput — 300–500 production pods handling continuous TV event streams
- **Cache**: In-memory + file-based cache of blacklisted channel IDs, refreshed from RDS periodically

### Users

- **Primary**: Vizio SmartCast TVs (millions of devices sending events)
- **Secondary**: Data engineering/analytics teams consuming downstream data lake
- **Operators**: Inscape DE team managing the service

---

## Target State

### Target Repository

`rebuilder-evergreen-tvevents` — a new repository. The legacy `evergreen-tvevents` codebase will not be modified.

### Goals

1. Remove the `cntools_py3`/`cnlib` dependency entirely — replace with standalone implementations
2. Produce a standalone Redis Python module (`rebuilder-redis-module`) that can be used independently
3. Replace AWS Kinesis Data Firehose with **Kafka** for event delivery
4. Migrate from Flask to **FastAPI** for native async support, automatic OpenAPI generation, and Pydantic validation
5. Upgrade to Python 3.12+
6. Add comprehensive `/ops/*` SRE diagnostic and remediation endpoints
7. Implement full unit test coverage with domain-realistic test data
8. Add Terraform infrastructure-as-code
9. Remove embedded PagerDuty (`pygerduty`), Stackdriver, and vendor-specific monitoring — use OTEL + external alerting
10. Replace file-based channel ID cache with Redis
11. Produce OpenAPI specification with full Pydantic response models and examples

### Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend | Python 3.12 / FastAPI | Native async, automatic OpenAPI, Pydantic validation |
| Database | PostgreSQL (AWS RDS) | Keep existing RDS for blacklist lookups |
| Cache | Redis (standalone module) | Replace file-based cache; standalone module for reuse |
| Message Queue | Apache Kafka | Replace Kinesis Firehose per org migration to Kafka |
| CI/CD | GitHub Actions | Continue existing CI tool |
| Auth | HMAC security hash (reimplemented) | Remove cnlib dependency; reimplement token_hash |
| Observability | OpenTelemetry → OTEL Collector | Keep OTEL, remove New Relic/PagerDuty direct integration |
| IaC | Terraform | Replace Helm-only deployment |

### Target Infrastructure

| Question | Answer |
|---|---|
| Target cloud provider | AWS (no cloud migration) |
| Target compute | AWS EKS (Kubernetes) |
| Containerization | Docker |
| Container orchestration | Kubernetes (EKS) |
| IaC tool | Terraform + Helm |
| Target regions | Same as current (AWS_REGION) |

### Architecture

- **Layered FastAPI service** with clear separation:
  - `api/` — route handlers with Pydantic request/response models
  - `domain/` — event type validation and transformation logic
  - `services/` — Kafka producer, RDS client, Redis cache client
  - `ops/` — SRE diagnostic and remediation endpoints
- **Standalone Redis module** (`rebuilder-redis-module`) — extracted, reusable Python package for Redis operations
- **Kafka producer** replaces Firehose delivery — sends to Kafka topics instead of Kinesis streams

### API Design

- FastAPI with automatic OpenAPI spec generation
- All endpoints return typed Pydantic response models
- `/v1/events` POST — receive TV event payloads (replaces POST `/`)
- `/health` — dependency-checking health endpoint (replaces `/status`)
- `/ops/*` — full SRE diagnostic and remediation suite

### Observability & SRE

- OpenTelemetry for traces, metrics, structured JSON logs
- Golden Signals (latency, traffic, errors, saturation) via middleware
- RED metrics (rate, errors, duration) per endpoint
- `/ops/status`, `/ops/health`, `/ops/metrics`, `/ops/config`, `/ops/dependencies`, `/ops/errors`
- `/ops/drain`, `/ops/cache/flush`, `/ops/circuits`, `/ops/loglevel`, `/ops/scale`
- No embedded PagerDuty/New Relic — alerting is an infrastructure concern

### Auth & RBAC

- HMAC security hash validation reimplemented (standalone, no cnlib)
- Admin endpoints (`/ops/*`) — internal only, not exposed via public gateway
- Service-to-service auth via IAM roles for Kafka and RDS access

### Dependency Contracts

| Dependency | Direction | Interface | Inside/Outside Rebuild | Fallback |
|---|---|---|---|---|
| AWS RDS PostgreSQL | Outbound | psycopg2 / asyncpg | Outside — keep existing | Return cached blacklist; degrade gracefully |
| Apache Kafka | Outbound | confluent-kafka producer | Inside — new | Queue locally + retry with backoff |
| Redis | Outbound | rebuilder-redis-module | Inside — new standalone module | Fallback to in-memory cache |

### Migration Strategy

- Parallel run: new service alongside legacy until validated
- Feature flag for traffic shifting
- Data delivery: Kafka topic mirrors Firehose data format for downstream compatibility

### Constraints

- Must preserve exact payload validation logic (HMAC hash, event type schemas)
- Must maintain backward-compatible output JSON format for downstream consumers
- No downtime during migration — parallel run required
- Team: Inscape Data Engineering

### Out of Scope

- Database schema changes to `tvevents_blacklisted_station_channel_map`
- Downstream data lake/analytics pipeline changes
- Kong API Gateway configuration
- Cloud provider migration (staying on AWS)
- Frontend (none exists)
