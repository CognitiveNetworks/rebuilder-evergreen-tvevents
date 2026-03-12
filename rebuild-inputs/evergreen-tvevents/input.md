# Rebuild Input

## Original Prompt

> Source all agent skills and config from rebuilder-template only. Remove the existing rebuilder-evergreen-tvevents files and repo as we are going to recreate and start over. Run the rebuilder process by running rebuilder-template to rebuild the evergreen-tvevents as the primary repo and the rebuilder-evergreen-template-repo-python as an adjacent repo. Build new context every time. We want to keep the file-cache and do not move it to Redis, we do not want to re-invent business logic. We want to use Kafka for Firehose and create a standalone RDS and Kafka python module outside the repo. We want to use FastAPI, OTEL auto instrumentation and write tests to cover that new functionality. We need to follow the rebuilder-evergreen-template-repo-python exactly for the pip-compile workflow, the entry point and environment-check.sh, tests, OTEL, Helm Charts and T1_Salt. Do not reference any other directories except for the ones I explicitly listed.

## Application Name

> evergreen-tvevents

## Repository / Source Location

> `rebuild-inputs/evergreen-tvevents/repo/` (cloned from https://github.com/CognitiveNetworks/evergreen-tvevents)

## Current Tech Stack Summary

> Python 3.10 Flask 3.1.1 web application served via Gunicorn with gevent workers. Uses PostgreSQL RDS for blacklist channel ID lookups with a 3-tier cache (memory → file → RDS). Sends processed telemetry events to up to 6 AWS Kinesis Firehose delivery streams. Deployed on AWS EKS with KEDA autoscaling (1–500 replicas). Uses cnlib/cntools_py3 shared library for Firehose client, security hash validation, and structured logging. Full OTEL instrumentation (manually configured TracerProvider, MeterProvider, LoggerProvider) exporting to New Relic.

## Current API Surface

> Two endpoints, no versioning, no OpenAPI documentation. POST `/` receives TV event payloads from SmartCast devices (requires tvid, client, h, EventType, timestamp params; T1_SALT security hash auth). GET `/status` returns health check. Known consumers: Vizio SmartCast TV devices; full consumer set is unknown (risk finding).

## Current Observability

> Full OTEL with TracerProvider, MeterProvider, LoggerProvider — all manually configured. Exports to New Relic via OTEL OTLP exporter. Custom metrics: DB connection counters, query duration histograms, cache read/write counters, Firehose send operations. Auto-instrumented: Flask, psycopg2, botocore, boto3-sqs, requests, urllib3. Request logging middleware. No formal SLOs/SLAs defined.

## Current Auth Model

> Machine-to-machine auth via T1_SALT security hash. TV devices include an `h` parameter computed from request parameters and a shared salt. Server validates using `cnlib.token_hash.security_hash_match`. No user auth, no RBAC, no OAuth. ACR MSK credentials (username/password) stored as environment variables.

## External Dependencies & Integrations

### Outbound Dependencies (services this app calls)

1. **AWS Kinesis Firehose** — boto3 SDK, up to 6 delivery streams, documented via env vars. Being replaced by Kafka.
2. **PostgreSQL RDS** — psycopg2 direct DB, blacklist channel lookups from `public.tvevents_blacklisted_station_channel_map`. Retained.
3. **AWS MSK (Kafka)** — referenced in environment-check.sh but not directly used in visible app code. Will become the primary event delivery mechanism.

### Inbound Consumers (services that call this app)

Vizio SmartCast TV devices. Full consumer set unknown — risk finding. Mitigation: backward-compatible API response shapes.

### Shared Infrastructure

- RDS PostgreSQL (`tvcdb-development.cognet.tv`, database `tvevents`) — shared with unknown other services
- Kinesis Firehose delivery streams — shared downstream pipeline infrastructure (being replaced by Kafka)

### Internal Libraries / Shared Repos

- **cnlib** (via cntools_py3) — `cnlib.firehose.Firehose`, `cnlib.token_hash.security_hash_match`, `cnlib.log`. Vendored in repo.

### Data Dependencies

Kinesis Firehose streams deliver to downstream analytics/storage (S3, Redshift, etc.). Kafka will replace this delivery mechanism. Downstream consumers of the data are outside rebuild scope.

## Age of Application

> Built on mature Flask patterns. Actively maintained — dependencies are relatively current (Flask 3.1.1, boto3 1.36.14, OTEL 1.31.1 from January 2025). But Python 3.10 is two major versions behind current.

## Why Rebuild Now

> Migration from Flask to FastAPI for async-native processing and automatic OpenAPI documentation. Migration from Kinesis Firehose to Kafka for event delivery. Standardization on the template-repo-python patterns (pip-compile, OTEL auto-instrumentation, uvicorn, environment-check structure, Helm chart templates) for consistency across the service fleet. Creation of reusable standalone RDS and Kafka modules to reduce duplication across services.

## Known Technical Debt

1. Python 3.10 — two major versions behind, missing performance and language improvements
2. Manual OTEL instrumentation — verbose, error-prone, should use auto-instrumentation
3. No OpenAPI spec — Flask doesn't auto-generate; FastAPI does
4. ThreadPoolExecutor parallelism — blocking threads for I/O; async would be more efficient
5. No visible unit tests — test infrastructure exists but coverage unclear
6. cnlib vendored as symlink — fragile dependency management
7. Hardcoded Firehose stream names via environment variables — no abstraction layer
8. Startup failure if RDS unreachable and cache file missing — no graceful degradation

## What Must Be Preserved

1. **T1_SALT security hash validation** — exact same algorithm via cnlib
2. **3-tier blacklist cache** — memory → file → RDS, including file cache at configurable path
3. **Event type classification** — NativeAppTelemetry, AcrTunerData, PlatformTelemetry with their specific validation rules
4. **Channel obfuscation logic** — blacklist + content-block flag checking
5. **Request validation** — required params, timestamp check, security hash
6. **POST `/` request/response contract** — backward-compatible with existing TV device firmware
7. **GET `/status` health endpoint** — backward-compatible
8. **All OTEL custom metrics** — DB connection, query duration, cache operations (using auto-instrumentation where possible)

## What Can Be Dropped

1. **Flask/Gunicorn/gevent** — replaced by FastAPI/uvicorn
2. **AWS Kinesis Firehose** — replaced by Kafka
3. **Manual OTEL configuration** — replaced by auto-instrumentation
4. **ThreadPoolExecutor** — replaced by async patterns
5. **Legacy Firehose stream names** — replaced by Kafka topic configuration

## Developer Context (Optional)

> The rebuild must follow the rebuilder-evergreen-template-repo-python patterns exactly — this is non-negotiable. The standalone RDS and Kafka Python modules should be designed as reusable libraries that other services in the fleet can consume. The file-based blacklist cache must be preserved as-is (not Redis) to avoid reinventing business logic. The cnlib shared library must continue to be used for T1_SALT security hash validation and structured logging.
