# Rebuild Input

## Application Name

evergreen-tvevents (tvevents-k8s)

## Repository / Source Location

https://github.com/CognitiveNetworks/evergreen-tvevents
Cloned to: `rebuild-inputs/evergreen-tvevents/repo`

## Current Tech Stack Summary

Python 3.10 Flask application serving TV event telemetry ingestion. Runs on AWS EKS with Gunicorn + gevent workers. Uses PostgreSQL (AWS RDS) for blacklisted channel lookups, AWS Kinesis Data Firehose (via cnlib wrapper) for event delivery to S3 data lake. Authentication via HMAC security hash (cnlib `token_hash`). OpenTelemetry instrumentation exported to New Relic via OTLP. Embedded PagerDuty alerting via `pygerduty`. Deployed via Helm charts with 300–500 production pod scaling.

## Current API Surface

- 2 endpoints: POST `/` (event ingestion) and GET `/status` (health check)
- No OpenAPI spec, no versioning
- HMAC security hash authentication on POST endpoint
- Primary consumer: Vizio SmartCast TVs via Kong API Gateway
- Internal health check consumers: Kubernetes probes

## Current Observability

- OpenTelemetry traces, metrics, and structured logs exported via OTLP HTTP to New Relic
- Custom OTEL counters: DB connections (4 counters), cache operations (2 counters), firehose sends (1 counter), payload validation (4 counters)
- PagerDuty integration via `pygerduty` (service ID: PSV1WEB)
- Health check: `/status` returns plain "OK" text — does not check dependencies
- No SLOs/SLAs defined
- No structured diagnostic endpoints

## Current Auth Model

- HMAC-based security hash: TVs compute hash from `tvid` + shared salt, service verifies via `cnlib.token_hash.security_hash_match(tvid, h_value, salt_key)`
- Salt loaded from `T1_SALT` environment variable
- No RBAC — single auth model for all TV clients
- No service-to-service auth scoping (AWS credentials used for Firehose/RDS access)

## External Dependencies & Integrations

### Outbound Dependencies (services this app calls)

| Service | Interface | Documented |
|---|---|---|
| AWS Kinesis Data Firehose (Evergreen stream) | boto3 via cnlib `firehose.Firehose` | Partially — env var `EVERGREEN_FIREHOSE_NAME` |
| AWS Kinesis Data Firehose (Legacy stream) | boto3 via cnlib `firehose.Firehose` | Partially — env var `LEGACY_FIREHOSE_NAME` |
| AWS Kinesis Data Firehose (Debug streams) | boto3 via cnlib `firehose.Firehose` | Partially — env vars `DEBUG_*_FIREHOSE_NAME` |
| AWS RDS PostgreSQL | psycopg2 direct connection | Partially — env vars `RDS_HOST/DB/USER/PASS/PORT` |

### Inbound Consumers (services that call this app)

- Vizio SmartCast TVs (millions of devices, via Kong API Gateway) — primary and known consumer
- Kubernetes liveness/readiness probes — `/status`
- Unknown other internal consumers — **risk finding**: no documentation of other API consumers exists

### Shared Infrastructure

- AWS RDS PostgreSQL `tvevents` database — at minimum the `tvevents_blacklisted_station_channel_map` table is shared with other services (details unknown)
- S3 bucket `cn-tvevents/<ZOO>/tvevents/` — written to by Firehose, read by downstream pipelines

### Internal Libraries / Shared Repos

| Library | Repo | Functions Used |
|---|---|---|
| cnlib (cntools_py3) | `git@github.com:CognitiveNetworks/cntools_py3.git` | `firehose.Firehose` — Kinesis Firehose wrapper; `token_hash.security_hash_match` — HMAC hash validation; `log.getLogger` — custom logger factory |

### Data Dependencies

- **Downstream S3 consumers**: Data lake pipelines read from S3 buckets written by Kinesis Firehose. Exact consumers unknown. Output JSON format is a contract.
- **Blacklist data source**: `tvevents_blacklisted_station_channel_map` table — source of truth for blacklisted channels. Unknown who writes to it (possibly admin tools or batch processes).

## Age of Application

- Originally built as part of the Inscape Evergreen platform (estimated 2018–2019 timeframe based on dependency versions)
- Actively maintained — recent commits include OTEL instrumentation, CVE remediation, dependency updates
- Containerized and migrated to Kubernetes (tvevents-k8s) from earlier deployment model

## Why Rebuild Now

1. **cntools_py3 dependency removal**: The cnlib git submodule is a maintenance burden — it bundles Redis, memcached, ZeroMQ, MySQL, and other libraries the app doesn't use, creates CI complexity with submodule initialization, and is a coupling point across multiple teams. The organization is moving away from this shared library.
2. **Firehose → Kafka migration**: The organization is standardizing on Apache Kafka for event streaming. The current Kinesis Firehose integration must be replaced.
3. **Standalone Redis module**: Other services need a reusable Redis client — extracting it from cnlib into a standalone package enables that.
4. **Modernization**: Flask → FastAPI for async support, automatic OpenAPI, Pydantic validation. Python 3.10 → 3.12+. Remove embedded vendor monitoring (PagerDuty, New Relic). Add SRE diagnostic endpoints.

## Known Technical Debt

1. **Security**: `T1_SALT` loaded from plain env var, not secrets manager. No constant-time hash comparison visible in app code (delegated to cnlib).
2. **Reliability**: File-based blacklist cache (`/tmp/.blacklisted_channel_ids_cache`) is fragile — pod restarts lose cache, not shared across pods. New connections opened per RDS query (no connection pooling).
3. **Maintainability**: cnlib git submodule frequently breaks CI. 80+ runtime dependencies including many unused OTEL instrumentors. Inline OTEL configuration rather than standard patterns.
4. **Operations**: No SRE diagnostic endpoints. `/status` returns "OK" regardless of dependency health. No graceful drain mechanism. Embedded PagerDuty client.
5. **Code quality**: pylint disables scattered throughout. No type annotations. Mutable default argument in `flatten_request_json`. No OpenAPI spec.

## What Must Be Preserved

1. **Payload validation logic**: HMAC security hash verification, required parameter checks, event-type-specific schema validation (ACR tuner data, platform telemetry, native app telemetry)
2. **Output JSON format**: Flattened JSON structure with specific key naming conventions (e.g., `tvevent_timestamp`, `tvevent_eventtype`, `paneldata_panelstate`) — downstream consumers depend on this exact format
3. **Channel obfuscation**: Blacklisted channel detection and content obfuscation with "OBFUSCATED" string
4. **Event type polymorphism**: Support for NATIVEAPP_TELEMETRY, ACR_TUNER_DATA, PLATFORM_TELEMETRY event types with type-specific validation and output generation
5. **RDS blacklist integration**: PostgreSQL query for blacklisted channel IDs with caching

## What Can Be Dropped

1. **cnlib/cntools_py3 dependency** — replace with standalone implementations
2. **AWS Kinesis Firehose delivery** — replace with Kafka
3. **pygerduty / PagerDuty SDK** — alerting becomes an infrastructure concern via OTEL + external monitoring
4. **google-cloud-monitoring** — legacy Stackdriver dependency, not used
5. **pymemcache** — memcached client from cnlib, not used by this app
6. **PyMySQL** — MySQL client from cnlib, not used by this app
7. **pyzmq** — ZeroMQ from cnlib, not used by this app
8. **python-consul** — Consul client from cnlib, not used by this app
9. **File-based blacklist cache** — replace with Redis
10. **Legacy Firehose routing** — SEND_LEGACY/SEND_EVERGREEN env var complexity
11. **gevent monkey-patching** — replace with native async (FastAPI/uvicorn)
12. **boto/boto3** — only used for Firehose via cnlib; Kafka replaces this
13. **Inline OTEL configuration** — use standard FastAPI OTEL integration patterns

## Developer Context (Optional)

- Team: Inscape Data Engineering (estimated 4–6 engineers)
- The app processes extremely high throughput (production scales to 300–500 pods)
- Timeline: Rebuild should be rapid — the app logic is relatively simple (validate → transform → deliver)
- The `rebuilder-redis-module` is a standalone deliverable that must be usable by other services independent of this rebuild
- **Do not reference tv-collection-services or vizio-automate directories** — this is a clean build
- Kafka should use `confluent-kafka` or equivalent production-grade Python Kafka library
