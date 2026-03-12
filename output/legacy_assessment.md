# Legacy Assessment

> **Reference document.** This is analysis output from the ideation process. It informs decisions but does not override developer-agent/skill.md.

## Application Overview

evergreen-tvevents is a high-throughput telemetry ingestion microservice deployed on AWS EKS that receives TV event data from Vizio SmartCast devices. It validates incoming HTTP POST requests using T1_SALT-based security hash authentication, classifies events into three types (NativeAppTelemetry, AcrTunerData, PlatformTelemetry), applies channel obfuscation using a 3-tier blacklist cache (in-memory dict → JSON file → PostgreSQL RDS), and forwards processed payloads to up to 6 AWS Kinesis Firehose delivery streams in parallel. Built with Python 3.10, Flask 3.1.1, Gunicorn + gevent, and KEDA autoscaling from 1 to 500 replicas. The service uses cnlib/cntools_py3 as a vendored shared library for Firehose client, security hash validation, and structured logging. Full OTEL instrumentation exports telemetry to New Relic.

## Architecture Health
- Rating: **Acceptable**
- The application follows a clean microservice pattern — single responsibility (telemetry ingestion), stateless request processing (cache is read-only from app's perspective), and clear data flow (validate → classify → obfuscate → forward).
- Separation of concerns is reasonable: `routes.py` handles HTTP, `utils.py` handles business logic, `dbhelper.py` handles data access, `event_type.py` encapsulates event classification. However, `utils.py` is doing too much — it combines request validation, Firehose configuration, payload generation, and delivery orchestration in a single 300+ line file.
- The 3-tier cache pattern (memory → file → DB) is well-designed and effective for the small dataset. The cache initialization at startup with a fallback to file is pragmatic.
- Coupling to AWS Firehose is direct — `cnlib.firehose.Firehose` is called throughout `utils.py` with no abstraction layer. Replacing the delivery mechanism requires touching all send logic.
- ThreadPoolExecutor for parallel Firehose sends is functional but represents a synchronous approach to an I/O-bound workload. Flask + gevent provides cooperative multitasking but not true async.
- The event type system uses a clean inheritance pattern with an abstract base class and a dispatch map — well-structured and extensible.

## API Surface Health
- Rating: **Poor**
- Only two endpoints: POST `/` and GET `/status`. Extremely minimal surface area.
- No OpenAPI specification — Flask does not auto-generate one, and none is checked in.
- No API versioning. The root path (`/`) as the primary business endpoint makes future versioning awkward.
- No Pydantic models or schema validation for request/response bodies — validation is manual string checking in `utils.py`.
- The POST endpoint combines multiple responsibilities: receiving diverse event types, validating security, processing business logic, and forwarding to multiple streams — all in a single route handler.
- Error responses use custom exception classes with status codes, which is good, but response shapes are not formally documented.
- No `/ops/*` diagnostic endpoints for SRE tooling.

## Observability & SRE Readiness
- Rating: **Acceptable**
- Comprehensive OTEL setup in `__init__.py`: TracerProvider, MeterProvider, LoggerProvider all properly configured with OTLP exporters and New Relic-compatible header injection.
- Custom application metrics in `dbhelper.py`: `DB_CONNECTION_COUNTER`, `DB_QUERY_DURATION` histogram, `CACHE_READ_COUNTER`, `CACHE_WRITE_COUNTER` — demonstrates domain-specific observability awareness.
- Auto-instrumentation for Flask, psycopg2, botocore, boto3-sqs, requests, urllib3 — covers the dependency tree.
- Request logging middleware logs method, path, content-length on every request.
- OTEL spans added to all DB operations (`_connect`, `_execute`, `fetchall_channel_ids`, `initialize_blacklisted_channel_ids_cache`, `blacklisted_channel_ids`).
- **Gaps:** No formal SLOs or SLAs. No `/ops/*` diagnostic endpoints. No structured error budget tracking. All OTEL setup is manual (48 lines of boilerplate) instead of auto-instrumentation. MeterProvider is configured but Golden Signals (latency p50/p95/p99, traffic, error rate, saturation) are not explicitly instrumented at the request level.

## Auth & Access Control
- Rating: **Acceptable**
- T1_SALT security hash is a functional machine-to-machine auth mechanism. The salt is stored as an environment variable, not hardcoded.
- `cnlib.token_hash.security_hash_match` provides the crypto implementation — keeping it in a shared library is appropriate.
- `validate_security_hash()` properly returns a TvEventsSecurityValidationError on mismatch with detailed logging.
- ACR MSK credentials (username/password) stored as environment variables — acceptable for Kubernetes Secrets-backed deployment.
- **Gaps:** No RBAC (not needed for machine-to-machine). No service-to-service auth for `/status` endpoint (typical for health checks). The T1_SALT is a single shared secret — if compromised, all devices are affected. No key rotation mechanism visible in code.

## Code & Dependency Health
- Rating: **Acceptable**
- **Python 3.10** — current LTS is 3.12 with 3.13 released. Two major versions behind. Missing: exception groups, tomllib, TaskGroup, performance improvements from 3.11/3.12.
- **Flask 3.1.1** — recent release, actively maintained. Not a health concern itself, but Flask is synchronous-first.
- **Gunicorn 23.0.0** + **gevent 24.11.1** — both current. Gevent monkey-patching adds complexity.
- **psycopg2-binary 2.9.10** — current. Binary distribution simplifies Docker builds.
- **boto3 1.36.14** — reasonably current (Jan 2025).
- **OTEL packages at 1.31.1** — very recent, matching the latest OTEL Python SDK.
- **cnlib/cntools_py3** — vendored as a symlink (`cnlib -> cntools_py3/cnlib`). This is fragile — symlinks can break during Docker builds, CI pipelines, and developer setups. The library provides critical functionality (Firehose, security hash, logging).
- `requirements.txt` is a flat pip install list (not pip-compiled with hashes), which creates reproducibility risks.
- No `pyproject.toml` `[project.dependencies]` section — dependencies are managed via requirements files only.

## Operational Health
- Rating: **Acceptable**
- Docker deployment with a clean Dockerfile: Python 3.10-bookworm base, cnlib built via setup.py, non-root `flaskuser` (UID 10000).
- `entrypoint.sh` properly sources `environment-check.sh`, creates AWS config, configures OTEL headers, initializes blacklist cache, and starts Gunicorn.
- `environment-check.sh` is thorough — validates 6 groups of environment variables (rds_vars, firehose_vars, acr_data_msk_vars, app_vars, always_required, otel_nr_vars) with clear error messages and `TEST_CONTAINER` mode.
- KEDA autoscaling configured for 1–500 replicas — appropriate for bursty telemetry workloads.
- Helm charts with values.yaml for deployment configuration.
- **Gaps:** No CI/CD pipeline visible in the repo. No integration tests. Startup is brittle — if RDS is unreachable and the cache file doesn't exist, the container fails with RuntimeError. No graceful degradation.

## Data Health
- Rating: **Good**
- Single table in scope: `public.tvevents_blacklisted_station_channel_map` with `channel_id` column (queried via `SELECT DISTINCT channel_id`).
- Simple, well-normalized schema — a lookup table with no relationships visible in the app code.
- Data volume is small enough to cache entirely in memory and as a JSON file — low migration complexity.
- Cache file format is JSON (written via `json.dump`, read via `json.load`) — portable and inspectable.
- No migration scripts visible, but schema is simple enough that manual management is low-risk.
- The 3-tier cache pattern provides resilience: if RDS is temporarily unavailable, the file cache serves data.

## Developer Experience
- Rating: **Poor**
- **Local development:** No `docker-compose.yml` for local stack. `env.list` provides development environment variables pointing to `tvcdb-development.cognet.tv` — requires VPN/network access to a real RDS instance.
- **Testing:** No visible test files in the repo's `tests/` directory. No test configuration. No pytest setup.
- **Documentation:** README.md exists but its content wasn't analyzed. No API documentation.
- **Onboarding:** A new developer needs to: understand Flask + gevent + Gunicorn, obtain RDS credentials, have AWS Firehose access, understand the cnlib symlink, understand T1_SALT configuration, and understand the event type system. High tribal knowledge barrier.
- **Dependency management:** Flat `requirements.txt` without hash pinning. No `requirements-dev.txt` visible with dev tools.
- **Code quality tools:** No linter, formatter, type checker, or CI quality gates visible.

## Infrastructure Health
- Rating: **Acceptable**
- Cloud Provider(s): AWS
- Containerized: Yes — Docker with Python 3.10-bookworm base
- IaC: Helm charts for Kubernetes deployment (values.yaml with KEDA, resource limits, service configuration)
- Managed Services: RDS PostgreSQL (blacklist data), Kinesis Firehose (event delivery), MSK Kafka (referenced but unclear usage)
- Provider Lock-in: **Medium** — boto3 SDK for Firehose is AWS-specific. cnlib.firehose.Firehose wraps boto3 Firehose client. RDS connection uses standard psycopg2 (portable). OTEL exports are provider-agnostic.
- Cloud Migration Impact: Not applicable — staying on AWS. However, replacing Firehose with Kafka (AWS MSK or standalone) reduces Firehose-specific lock-in.
- The Dockerfile is well-structured: multi-concern (CVE patches, cnlib build, requirements install, OTEL bootstrap), non-root user, specific Python version.
- HEALTHCHECK not defined in Dockerfile — relies on Kubernetes probes via Helm values.

## External Dependencies & Integration Health
- Rating: **Acceptable**
- Outbound Dependencies:
  1. AWS Kinesis Firehose (SDK via boto3/cnlib — being replaced by Kafka)
  2. PostgreSQL RDS (direct DB via psycopg2 — retained)
  3. AWS MSK (referenced in environment-check.sh credentials — unclear usage)
- Inbound Consumers: Vizio SmartCast TV devices — **Unknown full consumer set is a risk finding**
- Shared Infrastructure: RDS PostgreSQL shared with unknown services; Firehose streams shared downstream pipeline
- Internal Libraries: cnlib (via cntools_py3) — Firehose, security hash, logging
- Data Dependencies: Firehose → S3/Redshift downstream analytics (outside scope)
- Tightly Coupled: cnlib for security hash validation (must be preserved). Firehose through cnlib (being replaced by Kafka). No dependencies require modifying external services.
- The cnlib dependency is the highest risk: it's vendored, provides critical functionality, and its upstream maintenance status is unknown. However, only three modules are used: `firehose.Firehose` (being replaced), `token_hash.security_hash_match` (must be preserved), and `log` (must be preserved).

## Adjacent Repository Analysis

### rebuilder-evergreen-template-repo-python
- **Purpose:** Reference architecture template defining the target patterns for all rebuilt Python services in the fleet. Demonstrates FastAPI application factory, OTEL auto-instrumentation, pip-compile workflow, Helm chart templates with advanced helpers, entry point patterns, and environment-check structure.
- **Tech Stack:** Python 3.12, FastAPI, uvicorn, OTEL auto-instrumentation (FastAPIInstrumentor + 15 other instrumentors), cnlib (same shared library), pip-tools for dependency management
- **Integration Points:** No runtime integration — this is a structural template, not a running service. The evergreen-tvevents rebuild must adopt its patterns for:
  - Application factory (`create_app()` with `asynccontextmanager` lifespan)
  - Entry point (`app/main.py` with `from app import create_app; app = create_app()`)
  - OTEL setup (auto-instrumentation via `FastAPIInstrumentor.instrument_app(app)`)
  - Dockerfile (Python 3.12-bookworm, non-root `containeruser` UID 10000, port 8000, HEALTHCHECK)
  - entrypoint.sh (uvicorn startup, AWS config, OTEL header configuration)
  - environment-check.sh (simplified variable groups, TEST_CONTAINER support)
  - pip-compile workflow (`scripts/lock.sh` with `pip-compile --generate-hashes`)
  - Helm charts (values.yaml with deployment, service, HTTPRoute, secrets, KEDA, Dapr components, advanced template helpers)
- **Shared State:** None — template only
- **Coupling Assessment:** **Loose** — the template defines patterns, not shared runtime state. Coupling is structural: the rebuilt service must conform to the template's conventions.
- **Rebuild Recommendation:** Use as the architectural blueprint. Port evergreen-tvevents business logic into the template's structure. Do not treat as a separate service to deploy.

### Cross-Repo Integration Summary
- **Total integration points:** 0 runtime, 8+ structural patterns to adopt
- **Shared databases/schemas:** None
- **Shared infrastructure:** None (at runtime)
- **Risk if rebuilt independently:** If the primary is rebuilt without following the template patterns, it will diverge from fleet standards — deviations in OTEL setup, Helm charts, dependency management, and deployment patterns create operational toil.

## Summary
- Overall Risk Level: **Medium**
- Top 3 Risks:
  1. **Unknown inbound consumers** — the full set of services calling POST `/` is unknown; backward-compatible response shapes are critical
  2. **cnlib dependency** — vendored shared library with unclear upstream maintenance; security hash and logging functionality must be preserved through the rebuild
  3. **Firehose-to-Kafka migration** — replacing the delivery mechanism is the largest functional change; parity validation between Firehose and Kafka output is essential
- Strongest Assets to Preserve:
  1. **Event type classification system** — clean inheritance hierarchy with abstract base class and dispatch map; well-structured and extensible
  2. **3-tier blacklist cache** — pragmatic, effective, and battle-tested; the memory → file → RDS fallback chain provides resilience
  3. **Request validation pipeline** — thorough (required params, security hash, timestamp) with clear error types and status codes
  4. **OTEL instrumentation depth** — custom metrics on DB operations and cache operations demonstrate domain-aware observability; these should carry forward
