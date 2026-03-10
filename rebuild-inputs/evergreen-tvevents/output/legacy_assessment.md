# Legacy Assessment

## Application Overview

**tvevents-k8s** is a high-throughput TV event ingestion service that receives telemetry data from Vizio smart TVs. The service validates incoming payloads (HMAC hash verification, required parameter checks, event-type-specific validation), transforms and flattens the data, obfuscates blacklisted channel information, and delivers the processed events to AWS Kinesis Data Firehose streams for downstream analytics pipelines. It runs on AWS EKS at production scale (100–200 pods, CPU-autoscaled) and is built on Python 3.10 / Flask with Gunicorn + gevent workers.

The application is a single-repo Flask monolith (~1,169 lines of application code across 5 Python files) with a git submodule dependency on `cnlib` for Firehose delivery, HMAC validation, and logging. It has 18 test files covering utils, routes, event types, db helper, and initialization.

## Architecture Health

- **Rating:** Acceptable
- The architecture is a straightforward request-processing pipeline appropriate for the service's ingestion workload: receive → validate → transform → deliver. Components are organized into logical modules (`routes.py`, `utils.py`, `dbhelper.py`, `event_type.py`).
- Separation of concerns is reasonable: routes handle HTTP, utils handle validation/transformation/delivery, dbhelper handles RDS + cache, event_type handles per-type validation and output generation.
- The `event_type_map` dispatch pattern (`event_type.py:255-259`) is clean and extensible — adding a new event type requires only a new class and a map entry.
- **Coupling concern:** `utils.py` is a 418-line file that mixes validation, transformation, obfuscation, and Firehose delivery. These could be separated but function adequately as-is.
- **cnlib coupling:** The git submodule creates tight coupling to a shared library that is installed via `setup.py install` during Docker build. This is the primary architectural pain point — it forces coordinated releases and complicates the build pipeline.

## API Surface Health

- **Rating:** Poor
- Only 2 functional endpoints: `POST /` (ingestion) and `GET /status` (health check).
- No OpenAPI spec. No typed request/response models. No Pydantic or marshmallow schemas.
- No API versioning.
- No `/ops/*` diagnostic or remediation endpoints — does not meet current service bootstrap standards.
- Error handling uses a custom exception hierarchy (`TvEventsDefaultException` with `status_code = 400`) but returns unstructured JSON error responses.
- The `POST /` endpoint accepts a complex nested JSON payload (`TvEvent` + `EventData`) but the structure is validated procedurally rather than declaratively.

## Observability & SRE Readiness

- **Rating:** Acceptable
- **Strengths:** OpenTelemetry SDK is already integrated with comprehensive manual instrumentation:
  - Tracing: spans for DB connect, DB query, event type validation, Firehose delivery, obfuscation checks
  - Metrics: OTEL counters (request, DB connection, DB errors, DB read/write, cache read/write, event validation, Firehose delivery) and histograms (DB query duration)
  - Logs: OTEL log bridge via `LoggerProvider` + `OTLPLogExporter` to New Relic
  - Auto-instrumentation: Flask, psycopg2, botocore, boto3sqs, requests, urllib3
- **Gaps:**
  - No `/ops/metrics` endpoint — metrics are only available via OTEL export to New Relic, not on-demand
  - No Golden Signals or RED method metrics exposed via HTTP
  - No SLOs/SLAs defined
  - No error budgets
  - No `/ops/status` composite health verdict
  - No `/ops/dependencies` endpoint showing connectivity status
  - `GET /status` always returns "OK" regardless of dependency health — violates the "return 503 if unhealthy" standard

## Auth & Access Control

- **Rating:** Acceptable (with security concern)
- HMAC-based request validation is appropriate for device-to-server telemetry: `MD5(tvid + T1_SALT)` verified on every `POST /` request.
- T1_SALT is properly managed as a Kubernetes secret (not hardcoded).
- Region-based hash algorithm selection (MD5 for US, SHA-256 for EU via `eu-west-1` check in `token_hash.py:9-12`) adds geographic flexibility.
- **Security concern:** `token_hash.security_hash_match()` at line 35 uses `==` for hash comparison instead of constant-time `hmac.compare_digest()`. This is vulnerable to timing attacks. While the risk is low for device telemetry (attackers would need network proximity), it violates security best practices.
- No RBAC — appropriate for a headless device ingestion service.
- No service-to-service auth beyond HMAC.

## Code & Dependency Health

- **Rating:** Poor
- **cnlib dependency:** Git submodule (`cntools_py3/cnlib`) with 31 files. The application uses only 3 functions: `firehose.Firehose`, `token_hash.security_hash_match`, and `log.getLogger`. The remaining 28+ files are dead weight imported transitively.
- **Stale/unused dependencies in `pyproject.toml`:** `boto==2.49.0` (Python 2 era AWS SDK), `google-cloud-monitoring==0.28.1`, `pymemcache==4.0.0`, `PyMySQL==1.1.1`, `pyzmq==26.4.0`, `redis==6.0.0`, `fakeredis==2.29.0`, `python-consul==1.1.0`, `pygerduty==0.38.3` — none of these are imported by the application code.
- **Python version:** 3.10 — current but approaching end of security support (October 2026).
- **No type checking:** No mypy configuration, no type annotations in application code.
- **No linting:** Uses pylint (via dev dependencies) but no ruff, no pre-commit hooks.
- **No formatter enforcement:** black is in dev dependencies but no CI enforcement.
- **Test framework:** pytest 6.2.5 (latest is 8.x).
- **OTEL version alignment:** OTEL SDK 1.31.1 / instrumentation 0.52b1 — current and well-maintained.

## Operational Health

- **Rating:** Acceptable
- **Deployment:** Docker container on EKS with Helm charts. Reproducible builds with pinned base image (`python:3.10-bookworm@sha256:...`). Non-root user in container.
- **CI/CD:** GitHub Actions workflows for commit checks, container build/push, pre-release builds. ECR as container registry. Pod identity management scripts.
- **Container build concern:** `cnlib` installed via `setup.py install` during Docker build — a fragile legacy pattern.
- **entrypoint.sh:** Properly sources `environment-check.sh`, configures AWS, enables OTEL conditionally, initializes blacklist cache from RDS before starting Gunicorn.
- **environment-check.sh:** Validates 30+ required environment variables before startup, with TEST_CONTAINER mode for local dev (disables OTEL).
- **Helm charts:** Custom chart structure (not using template repo's chart templates). Values include per-environment SHA refs, OTEL config, application config, scaling parameters.
- **Scaling:** CPU-based HPA with 100–200 pod range, 70% CPU threshold, aggressive scale-up (50%/15s), gradual scale-down (25%/30s).
- **Health checks:** Liveness probe on `/status:8000` (90s initial delay, 90s period), readiness probe (37s initial delay, 17s period). Both just check for "OK" — no dependency health verification.
- **No graceful shutdown:** No drain mechanism, no connection pool cleanup on SIGTERM.

## Data Health

- **Rating:** Good
- **Schema:** Single read-only table `public.tvevents_blacklisted_station_channel_map` with `channel_id` column. Simple, normalized, single-purpose.
- **File cache:** `/tmp/.blacklisted_channel_ids_cache` — JSON array of channel IDs. Populated from RDS at startup (via `entrypoint.sh`) and on cache miss. Write-through pattern.
- **No migrations:** The service does not own the schema — it only reads from a shared table. No migration complexity.
- **Event payload:** Nested JSON (`TvEvent` + `EventData`) is well-structured but not schema-validated at the transport layer (no JSON Schema at API boundary, only procedural validation).

## Developer Experience

- **Rating:** Poor
- **Local setup:** Requires Docker, cnlib submodule initialization, RDS connectivity (or mocked), Firehose connectivity (or mocked), and 30+ environment variables. No `docker-compose.yml` for full local stack.
- **No `.env.example`:** Environment variables are documented only in `environment-check.sh` and `charts/values.yaml`.
- **Testing:** 18 test files exist but test discovery requires `pytest-pythonpath` configuration. Tests mock cnlib functions.
- **No OpenAPI spec:** Developers must read code to understand the API contract.
- **Onboarding friction:** cnlib submodule, lack of documentation, complex environment setup, no README with quick-start instructions.

## Infrastructure Health

- **Rating:** Acceptable
- **Cloud Provider(s):** AWS
- **Containerized:** Yes — Docker on AWS EKS (Kubernetes)
- **IaC:** Helm charts (in `charts/`). No Terraform for infrastructure resources (RDS, Firehose, networking).
- **Managed Services:**
  - AWS RDS PostgreSQL — blacklisted channel ID lookups
  - AWS Kinesis Data Firehose — event delivery (4 streams)
  - AWS ECR — container registry
  - AWS EKS — Kubernetes orchestration
- **Provider Lock-in:** Medium
  - `boto3`/`botocore` SDK used directly for Firehose (via cnlib)
  - AWS-specific Firehose delivery stream names in environment config
  - AWS RDS connection via `psycopg2` (portable — PostgreSQL is provider-agnostic)
  - No cloud migration planned — staying on AWS
- **Findings:**
  - No Terraform for RDS, Firehose, or networking resources — infrastructure provisioning is outside this repo
  - Helm chart structure is custom, not aligned with template repo's chart templates
  - Pod identity management scripts in `.github/scripts/` for EKS IRSA

## External Dependencies & Integration Health

- **Rating:** Acceptable
- **Outbound Dependencies:**
  - AWS Kinesis Data Firehose — via `cnlib.firehose.Firehose` (boto3 SDK). Tightly coupled through cnlib. Being replaced by Kafka.
  - AWS RDS PostgreSQL — via `psycopg2` direct connection. Loosely coupled (single read-only query).
- **Inbound Consumers:**
  - Vizio Smart TVs — high-volume POST requests. Payload format is the de facto contract.
  - Kubernetes probes — GET /status for health checks.
- **Shared Infrastructure:**
  - AWS RDS PostgreSQL — `tvevents_blacklisted_station_channel_map` table potentially shared with other services.
  - AWS Kinesis Data Firehose streams — shared delivery streams consumed by downstream pipelines.
- **Internal Libraries:**
  - `cnlib` (git submodule) — provides `firehose.Firehose`, `token_hash.security_hash_match`, `log.getLogger`. Tightly coupled — requires `setup.py install` during build.
- **Data Dependencies:**
  - Downstream data pipeline reads from Firehose → S3 buckets. Changing delivery mechanism (Firehose → Kafka) requires downstream coordination.
- **Tightly Coupled:** `cnlib` — cannot be stubbed without code changes. Being eliminated in rebuild.
- **Risk:** Downstream pipeline dependency on Firehose delivery format. Kafka delivery must produce equivalent output format.

## Adjacent Repository Analysis

### evergreen-template-repo-python

- **Purpose:** Organizational reference template for Python service operational files. Defines standard patterns for Dockerfile, entrypoint.sh, environment-check.sh, pip-compile workflow, Helm chart templates, OTEL configuration, and project structure.
- **Tech Stack:** Python 3.10, Flask 3.1.1, Gunicorn 23.0.0, OTEL SDK 1.31.1, pip-tools 7.4.1
- **Integration Points:** No runtime integration. Pattern reference only.
- **Shared State:** None
- **Coupling Assessment:** Loose — template provides patterns to follow, not code to import or APIs to call.
- **Rebuild Recommendation:** Use as adjacent reference for operational file patterns. Do not absorb into rebuild. Key patterns to adopt:
  - `Dockerfile` structure (pinned base image, non-root user, `opentelemetry-bootstrap`)
  - `entrypoint.sh` (environment-check, OTEL conditional, AWS config)
  - `environment-check.sh` (variable group validation with TEST_CONTAINER mode)
  - `scripts/lock.sh` (pip-compile workflow: `pyproject.toml` → `requirements.txt`)
  - `charts/` (Helm chart templates with deployment, service, HTTPRoute, secrets, OTEL collector, scaling)
  - `pyproject.toml` (dependency management with dev extras)

### Cross-Repo Integration Summary

- **Total integration points:** 0 (pattern reference only)
- **Shared databases/schemas:** None
- **Shared infrastructure:** None
- **Risk if rebuilt independently:** None — template repo is read-only reference

## Summary

- **Overall Risk Level:** Medium
- **Top 3 Risks:**
  1. **cnlib elimination** — Must replace Firehose delivery, HMAC validation, and logging without breaking the ingestion pipeline. All three functions are well-understood and replaceable.
  2. **Firehose → Kafka migration** — Downstream pipeline consumers currently read from Firehose → S3. Kafka delivery must produce equivalent output format and topic routing (evergreen, legacy, debug variants).
  3. **High-scale service** — 100–200 pods in production. Any regression in the rebuild's request handling performance or correctness directly impacts TV telemetry data collection.
- **Strongest Assets to Preserve:**
  1. **Event type dispatch pattern** (`event_type_map`) — clean, extensible, well-tested
  2. **Business logic** — validation, transformation, obfuscation logic is correct and battle-tested at scale
  3. **File-based cache** — simple, effective, no infrastructure dependency for blacklist lookups
  4. **OTEL instrumentation foundation** — tracing, metrics, and log bridge already wired (upgrade to auto-instrumentation)
  5. **Environment variable validation** (`environment-check.sh`) — prevents misconfigured deployments from starting
