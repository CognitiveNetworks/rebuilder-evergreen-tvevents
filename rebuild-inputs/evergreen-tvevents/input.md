# Rebuild Input

## Original Prompt

> Please ensure you source all agent skills and config. You are going to run the rebuilder process by cloning the rebuilder template into a new repo called rebuilder-evergreen-tvevents. Once you have cloned that you're going to rebuild the evergreen-tvevents as the primary repo and the evergreen-template-repo-python (https://github.com/CognitiveNetworks/evergreen-template-repo-python) as an adjacent repo in rebuilder-evergreen-tvevents. Once you have the new repo setup, rebuilder-evergreen-tvevents, you will start the rebuilder process following all steps in that repo. 1. There are dependencies in the evergreen-template-repo-python that need to be followed and produce the process that allows us to use pip compile to use the requirement.txt file, which is in the evergreen-template-repo-python repo. 2. Things like entry point, environment-check.sh, tests and Otel, Helm Charts, T1_Salt etc., need to be followed. 3. Keep the file-cache and do not move it to Redis, we do not want to re-invent business logic. 4. Ensure we use Kafka for Firehose and create a standalone RDS and Kafka python module outside the repo. 5. Use FastAPI, OTEL auto instrumentation and write tests to cover that new functionality. 6. When rebuilding you will not reference other builds for context, we are building new context every time.

## Application Name

> tvevents-k8s (Evergreen TV Events Collector)

## Repository / Source Location

> `rebuild-inputs/evergreen-tvevents/repo/` (cloned from `CognitiveNetworks/tvevents-k8s`)
> Adjacent: `rebuild-inputs/evergreen-tvevents/adjacent/evergreen-template-repo-python/` (cloned from `CognitiveNetworks/evergreen-template-repo-python`)

## Current Tech Stack Summary

> Python 3.10 Flask monolith running on Gunicorn with gevent workers behind an EKS (Kubernetes) cluster on AWS. Uses PostgreSQL (AWS RDS) for blacklisted channel ID lookups with a file-based cache at `/tmp/.blacklisted_channel_ids_cache`. Delivers processed TV event data to AWS Kinesis Data Firehose streams (evergreen + legacy). Depends on the `cnlib` shared library (git submodule at `cntools_py3/cnlib`) for Firehose delivery (`cnlib.firehose`), HMAC security hash validation (`cnlib.token_hash`), and logging (`cnlib.log`). OTEL instrumentation (tracing, metrics, logs) is already present with OTLP HTTP exporters to New Relic. Authentication uses HMAC MD5 hash of `tvid + T1_SALT` for request validation.

## Current API Surface

> 3 endpoints total:
> - `POST /` — Primary ingestion endpoint. Receives TV event payloads (JSON), validates required params, verifies HMAC security hash, validates event type-specific data, flattens/transforms output, obfuscates blacklisted channels, and delivers to Firehose streams.
> - `GET /status` — Simple health check returning "OK".
> - Error handler for `TvEventsCatchallException`.
>
> No OpenAPI spec. No `/ops/*` diagnostic endpoints. No Pydantic models. Authentication is HMAC-based (`T1_SALT`). Consumers are Vizio smart TVs sending telemetry data.

## Current Observability

> OpenTelemetry SDK is already integrated with OTLP HTTP exporters for traces, metrics, and logs to New Relic. Manual OTEL instrumentation exists throughout (tracer spans, metric counters/histograms for DB operations, cache operations, event type validation, Firehose delivery). Flask auto-instrumentation via `FlaskInstrumentor`. Psycopg2, botocore, boto3sqs, requests, and urllib3 auto-instrumentation. No SLOs/SLAs defined. No `/ops/metrics` endpoint. No Golden Signals or RED method metrics exposed. Failure detection relies on New Relic dashboards and alerts.

## Current Auth Model

> HMAC-based request validation. Each TV sends a `tvid` and an `h` (hash) parameter. The server computes `MD5(tvid + T1_SALT)` and compares it to the provided hash using `cnlib.token_hash.security_hash_match()`. The `T1_SALT` is an environment variable injected via Kubernetes secrets. Security concern: The comparison uses `==` (not constant-time `hmac.compare_digest()`). Region-based hash algorithm selection: MD5 for US, SHA-256 for EU (`eu-west-1`).

## External Dependencies & Integrations

### Outbound Dependencies (services this app calls)

> - **AWS Kinesis Data Firehose** — via `cnlib.firehose.Firehose` (boto3 SDK). Delivers processed event data to up to 4 Firehose streams (evergreen, legacy, debug-evergreen, debug-legacy).
> - **AWS RDS PostgreSQL** — via `psycopg2` direct connection. Queries `public.tvevents_blacklisted_station_channel_map` for blacklisted channel IDs. Connection params from env vars (`RDS_HOST`, `RDS_DB`, `RDS_USER`, `RDS_PASS`, `RDS_PORT`).

### Inbound Consumers (services that call this app)

> - **Vizio Smart TVs** — Send `POST /` requests with TV event telemetry data (ACR_TUNER_DATA, NATIVEAPP_TELEMETRY, PLATFORM_TELEMETRY event types). High volume (~100-200 pods in production).
> - **Load Balancer / Kubernetes Ingress** — Calls `GET /status` for health checks.

### Shared Infrastructure

> - **AWS RDS PostgreSQL** — The `tvevents_blacklisted_station_channel_map` table may be shared with other services.
> - **AWS Kinesis Data Firehose streams** — Shared delivery streams consumed by downstream data pipeline services.

### Internal Libraries / Shared Repos

> - **cnlib** (`cntools_py3/cnlib`) — Git submodule. Used for:
>   - `cnlib.firehose.Firehose` — Kinesis Data Firehose client with batching and retry
>   - `cnlib.token_hash.security_hash_match` — HMAC security hash validation
>   - `cnlib.token_hash.security_hash_token` — Hash generation
>   - `cnlib.log` — Logging utility (wraps Python `logging`)

### Data Dependencies

> - **Downstream data pipeline** — Kinesis Firehose streams deliver data to S3 buckets (`cn-tvevents/<ZOO>/tvevents/`) for downstream ETL/analytics processing.

## Age of Application

> Legacy application, actively maintained. Runs at high scale in production (100-200 pods). Recent updates include OTEL instrumentation additions and CVE patches.

## Why Rebuild Now

> 1. Dependency on deprecated `cnlib` shared library (git submodule) that creates tight coupling and deployment friction.
> 2. Kinesis Data Firehose is being replaced by Apache Kafka (AWS MSK) across the platform.
> 3. No OpenAPI spec, no Pydantic models, no `/ops/*` diagnostic endpoints — does not meet current service bootstrap standards.
> 4. Security concern: HMAC comparison uses `==` instead of constant-time comparison.
> 5. Flask is being replaced by FastAPI as the standard framework for new services.
> 6. Need to align with `evergreen-template-repo-python` patterns (Dockerfile, entrypoint, environment-check, pip-compile, Helm charts).

## Known Technical Debt

> 1. **cnlib dependency** — Git submodule coupling; `setup.py install` during Docker build.
> 2. **No constant-time HMAC comparison** — `token_hash.security_hash_match()` uses `==`.
> 3. **No OpenAPI spec** — No typed request/response models.
> 4. **No `/ops/*` endpoints** — Missing SRE diagnostic and remediation endpoints.
> 5. **Firehose coupling** — Direct AWS Firehose integration instead of Kafka.
> 6. **Missing quality gates** — No mypy, no ruff, limited test coverage tooling.
> 7. **Stale dependencies** — `boto==2.49.0`, `google-cloud-monitoring==0.28.1`, `pymemcache`, `PyMySQL`, `pyzmq`, `redis`, `fakeredis` — all unused by this service.
> 8. **No graceful shutdown** — No drain mechanism, no connection pool cleanup.

## What Must Be Preserved

> 1. **File-based cache** — `/tmp/.blacklisted_channel_ids_cache` for blacklisted channel IDs. Do NOT move to Redis.
> 2. **Business logic** — Event type validation (ACR_TUNER_DATA, NATIVEAPP_TELEMETRY, PLATFORM_TELEMETRY), payload flattening, channel obfuscation logic. Port directly, do not re-invent.
> 3. **HMAC authentication** — `T1_SALT`-based hash validation (but fix to use constant-time comparison).
> 4. **Event type mapping** — `event_type_map` dispatch pattern for event-type-specific validation and output generation.
> 5. **Channel blacklist obfuscation** — Obfuscate `channelid`, `programid`, `channelname` for blacklisted channels.
> 6. **Debug topic routing** — Separate debug vs production delivery paths.

## What Can Be Dropped

> 1. **cnlib dependency** — Replace `firehose.Firehose` with standalone Kafka module, replace `token_hash` with inline HMAC module, replace `cnlib.log` with standard Python logging.
> 2. **Kinesis Data Firehose** — Replace with Apache Kafka (AWS MSK).
> 3. **Unused dependencies** — boto (v2), google-cloud-monitoring, pymemcache, PyMySQL, pyzmq, redis, fakeredis, python-consul, pygerduty.
> 4. **`setup.py install` for cnlib** — Eliminated with cnlib removal.

## Developer Context (Optional)

> **Overrides from user:**
> 1. Use **FastAPI** (not Flask) as the web framework.
> 2. Use **OTEL auto-instrumentation** (opentelemetry-instrument).
> 3. Write **tests** to cover new FastAPI functionality.
> 4. Follow **evergreen-template-repo-python** patterns strictly: pip-compile, entrypoint.sh, environment-check.sh, Helm charts, Dockerfile.
> 5. Create **standalone RDS Python module** (`output/rebuilder-rds-module/`) outside the main service code.
> 6. Create **standalone Kafka Python module** (`output/rebuilder-kafka-module/`) outside the main service code.
> 7. **Do not reference other builds** for context — build fresh context every time.
