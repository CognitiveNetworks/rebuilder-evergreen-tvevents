# Modernization Opportunities

## Opportunity 1: Replace Flask with FastAPI

**Pain Point:** No OpenAPI spec, no typed request/response models, no Pydantic validation. API contract is undocumented. Service bootstrap standards require Pydantic `response_model` on every endpoint and `json_schema_extra` examples.

**Current State:** Flask 3.1.1 with Gunicorn + gevent. No typed models. Error responses are unstructured JSON. Payload validation is procedural (manual checks in `utils.py`). No OpenAPI/Swagger UI.

**Target State:** FastAPI with Uvicorn. Pydantic models for all request/response bodies. Auto-generated OpenAPI spec with Swagger UI. Typed error responses. Declarative payload validation where possible, preserving legacy validation logic for business rules.

**Migration Path:**
1. Define Pydantic models for `TvEvent`, `EventData` variants, and response types
2. Convert Flask routes to FastAPI path operations with `response_model`
3. Replace Gunicorn + gevent with Uvicorn (or Gunicorn with UvicornWorker)
4. Port `before_request` logging to FastAPI middleware
5. Port error handlers to FastAPI exception handlers
6. Update entrypoint.sh to launch Uvicorn instead of Gunicorn

**Risks:**
- Payload backward compatibility — TVs send payloads in a specific format; Pydantic validation must not reject valid legacy payloads
- Performance — must maintain throughput at 100-200 pod scale
- gevent compatibility — FastAPI uses asyncio, not gevent; verify no gevent-specific patterns exist

**Impact:** High — enables OpenAPI spec, typed models, Swagger UI, and contract testing

---

## Opportunity 2: Replace Kinesis Data Firehose with Apache Kafka (AWS MSK)

**Pain Point:** Platform is migrating from Kinesis Data Firehose to Apache Kafka (AWS MSK). Current Firehose integration is tightly coupled via `cnlib.firehose.Firehose` git submodule.

**Current State:** Events delivered to up to 4 Firehose streams via `cnlib.firehose.Firehose` (boto3 `put_record_batch`). ThreadPoolExecutor for parallel delivery. Retry logic with configurable limits. Environment variables control which streams are active (`SEND_EVERGREEN`, `SEND_LEGACY`).

**Target State:** Events delivered to Apache Kafka topics via standalone `kafka-module` Python package. Confluent Kafka client (`confluent-kafka`) with SASL/SCRAM authentication. OTEL instrumentation. Same routing logic (evergreen/legacy/debug variants) mapped to Kafka topics.

**Migration Path:**
1. Create standalone `rebuilder-kafka-module` with `KafkaProducerClient` class
2. Map Firehose stream names to Kafka topic names in environment configuration
3. Replace `send_to_valid_firehoses()` with `send_to_valid_topics()` using Kafka producer
4. Preserve debug routing logic (pre-obfuscation data to debug topics)
5. Update environment-check.sh with Kafka-specific variables (bootstrap servers, SASL credentials)
6. Coordinate with downstream pipeline team for Kafka consumer setup

**Risks:**
- Downstream pipeline must be ready to consume from Kafka before cutover
- Kafka delivery semantics differ from Firehose (at-least-once vs buffered batch)
- SASL/SCRAM credential management adds operational complexity

**Impact:** Critical — required by platform migration mandate

---

## Opportunity 3: Eliminate cnlib Git Submodule Dependency

**Pain Point:** `cnlib` is a shared library installed as a git submodule via `setup.py install` during Docker build. The application uses only 3 functions from 31+ files. This creates tight coupling, build friction, and version conflicts.

**Current State:** `cntools_py3/cnlib` submodule provides:
- `cnlib.firehose.Firehose` — Kinesis Data Firehose client with batching and retry
- `cnlib.token_hash.security_hash_match` — HMAC hash validation (`==` comparison)
- `cnlib.log.getLogger` — Logging wrapper around Python `logging`

**Target State:**
- Firehose client → replaced by standalone Kafka module (Opportunity 2)
- `token_hash` → inline `security.py` module with `hmac.compare_digest()` (fixes timing attack vulnerability)
- `cnlib.log` → standard Python `logging` (no wrapper needed)

**Migration Path:**
1. Create `app/security.py` with `security_hash_token()` and `security_hash_match()` using `hmac.compare_digest()`
2. Preserve region-based hash algorithm selection (MD5 US, SHA-256 EU)
3. Replace `from cnlib.cnlib import firehose, token_hash` imports throughout
4. Replace `from cnlib.cnlib import log` with `import logging`
5. Remove `cntools_py3/` submodule, `.gitmodules`, and `cnlib` symlink
6. Remove `setup.py install` step from Dockerfile

**Risks:**
- Hash algorithm parity — must produce identical hashes for backward compatibility with TV firmware
- Logging format changes — ensure structured log output matches existing format

**Impact:** High — eliminates submodule coupling, fixes security vulnerability, simplifies Docker build

---

## Opportunity 4: Add /ops/* Diagnostic and Remediation Endpoints

**Pain Point:** No operational endpoints beyond `GET /status` (which always returns "OK"). Service bootstrap standards require 11 `/ops/*` endpoints for SRE agent integration. Operations team must SSH or read logs to understand system state.

**Current State:** Single `GET /status` endpoint returns "OK" regardless of dependency health. No `/ops/metrics`, no `/ops/dependencies`, no `/ops/drain`, no `/ops/config`. Health check does not verify RDS or Kafka connectivity.

**Target State:** Full `/ops/*` endpoint suite:
- **Diagnostics:** `/ops/status` (composite health verdict), `/ops/health` (dependency-aware), `/ops/metrics` (Golden Signals + RED), `/ops/config` (runtime config), `/ops/dependencies` (connectivity status), `/ops/errors` (recent error summary)
- **Remediation:** `/ops/drain` (graceful shutdown), `/ops/cache/flush` (clear blacklist cache), `/ops/circuits` (circuit breaker state), `/ops/loglevel` (runtime log level), `/ops/scale` (if applicable)

**Migration Path:**
1. Define Pydantic response models for each `/ops/*` endpoint
2. Implement diagnostics endpoints with real dependency health checks (RDS ping, Kafka connectivity)
3. Implement drain mechanism with health check 503 response during shutdown
4. Implement cache flush endpoint for blacklist cache
5. Wire Golden Signals metrics (latency, traffic, errors, saturation) into `/ops/metrics`
6. Add RED method metrics (rate, errors, duration p50/p95/p99)

**Risks:**
- `/ops/*` endpoints must be available even when the service is degraded — they cannot depend on the same middleware that might be failing
- Drain endpoint must coordinate with Kubernetes graceful shutdown

**Impact:** High — required for SRE agent integration and service bootstrap compliance

---

## Opportunity 5: OTEL Auto-Instrumentation

**Pain Point:** Current OTEL instrumentation is manual — explicit `Psycopg2Instrumentor().instrument()`, `FlaskInstrumentor().instrument_app(app)`, etc. in `app/__init__.py`. This is verbose and requires code changes when adding new instrumented libraries.

**Current State:** Manual OTEL setup in `create_app()`:
- 6 explicit instrumentor calls (Psycopg2, Botocore, Boto3SQS, Requests, URLLib3, Flask)
- Manual `TracerProvider`, `MeterProvider`, `LoggerProvider` configuration
- Manual span creation throughout business logic

**Target State:** OTEL auto-instrumentation via `opentelemetry-instrument` CLI wrapper in entrypoint.sh. `opentelemetry-bootstrap` installs required instrumentation packages automatically. Manual spans retained only for business-specific tracing (event type processing, obfuscation decisions).

**Migration Path:**
1. Add `opentelemetry-instrument` to entrypoint.sh command
2. Run `opentelemetry-bootstrap` in Dockerfile to install instrumentation packages
3. Remove manual instrumentor calls from application code
4. Keep manual spans for domain-specific tracing
5. Configure via environment variables (OTEL_SERVICE_NAME, OTEL_EXPORTER_*, etc.)
6. Set `OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED=true` in Helm values

**Risks:**
- Auto-instrumentation may add overhead from instrumenting libraries that don't need it
- Must verify FastAPI auto-instrumentation produces equivalent trace data to manual Flask instrumentation

**Impact:** Medium — reduces boilerplate, aligns with template repo pattern

---

## Opportunity 6: Align Operational Files with Template Repo Patterns

**Pain Point:** Current Dockerfile, entrypoint.sh, environment-check.sh, Helm charts, and dependency management do not follow the `evergreen-template-repo-python` patterns. This creates inconsistency across services and complicates operational procedures.

**Current State:**
- Dockerfile installs cnlib via `setup.py install`, has CVE-specific apt-get packages
- `entrypoint.sh` uses Gunicorn with gevent, has service-specific cache initialization
- `environment-check.sh` checks Firehose-specific variables
- Helm charts use custom structure (not template chart templates)
- Dependencies managed via `pyproject.toml` + `requirements.txt` but without `pip-compile` workflow

**Target State:**
- Dockerfile follows template pattern: pinned base image, pip install from compiled `requirements.txt`, `opentelemetry-bootstrap`, non-root user
- `entrypoint.sh` follows template pattern: source environment-check, AWS config, OTEL conditional, launch Uvicorn
- `environment-check.sh` follows template pattern: grouped variable validation with TEST_CONTAINER mode, Kafka variables instead of Firehose
- Helm charts use template chart templates (Deployment, Service, HTTPRoute, ExternalSecret, OtelCollector, etc.)
- `scripts/lock.sh` uses `pip-compile` to generate `requirements.txt` from `pyproject.toml`

**Migration Path:**
1. Copy template repo's `scripts/lock.sh` and adapt
2. Restructure `pyproject.toml` with only needed dependencies
3. Run `pip-compile` to generate `requirements.txt` with hashes
4. Adapt Dockerfile from template, removing cnlib steps, adding FastAPI/Uvicorn
5. Adapt entrypoint.sh for Uvicorn and Kafka environment
6. Rewrite environment-check.sh with Kafka variable groups
7. Port Helm charts to template chart templates with tvevents-specific values

**Risks:**
- Helm chart template migration may require values.yaml restructuring
- pip-compile hash pinning may conflict with some packages

**Impact:** Medium — standardization enables consistent operations across services

---

## Opportunity 7: Create Standalone RDS Python Module

**Pain Point:** Database access is embedded directly in `app/dbhelper.py` with manual connection management, no connection pooling, and no retry logic with exponential backoff.

**Current State:** `TvEventsRds` class in `dbhelper.py` creates a new psycopg2 connection for every query, with no connection pooling. Connection params from individual environment variables. Manual OTEL span creation for DB operations.

**Target State:** Standalone `rebuilder-rds-module` package with:
- Connection pooling
- Retry logic with exponential backoff and jitter
- OTEL instrumentation
- Health check method
- Proper connection lifecycle management (close on shutdown)

**Migration Path:**
1. Create `output/rebuilder-rds-module/` with `pyproject.toml`, `src/rds_module/`, `tests/`
2. Implement `RdsClient` class with connection pool, retry, OTEL, health check
3. Refactor `app/dbhelper.py` to use `RdsClient` instead of direct psycopg2
4. Preserve file-cache logic in application code (not in the module)

**Risks:**
- Connection pool sizing must be validated at 100-200 pod scale
- Module versioning and distribution (PyPI or vendored)

**Impact:** Medium — improves reliability and reusability

---

## Opportunity 8: Add Comprehensive Quality Gates

**Pain Point:** No mypy, no ruff, limited test tooling. Legacy tests exist but no coverage enforcement, no complexity checks, no dead code detection.

**Current State:** pylint in dev dependencies (not enforced in CI). black for formatting (not enforced). pytest 6.2.5. No mypy, no ruff, no coverage thresholds, no pip-audit.

**Target State:**
- **Linting:** ruff (replaces pylint + isort + flake8)
- **Formatting:** ruff format (replaces black)
- **Type checking:** mypy with strict mode
- **Testing:** pytest 8.x with pytest-cov, pytest-asyncio (for FastAPI)
- **Coverage:** minimum threshold enforced in CI
- **Security:** pip-audit for dependency CVE scanning
- **CI pipeline:** lint → test → build → scan stages

**Migration Path:**
1. Configure ruff in `pyproject.toml` with appropriate rules
2. Configure mypy with `strict = true`
3. Add pytest-cov with coverage threshold
4. Add pip-audit to CI
5. Configure GitHub Actions CI workflow

**Risks:**
- mypy strict mode may require significant type annotation work
- Legacy business logic ported from untyped code may need type stubs

**Impact:** Medium — prevents regressions, improves maintainability
