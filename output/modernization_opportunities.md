# Modernization Opportunities

> **Reference document.** This is analysis output from the ideation process. It informs decisions but does not override developer-agent/skill.md.

## 1. Modernization Category Table

| # | Category | Opportunity | Impact | Effort | Priority |
|---|---|---|---|---|---|
| 1 | Framework & Runtime | Flask → FastAPI migration | High | High | P0 |
| 2 | Framework & Runtime | Python 3.10 → 3.12 upgrade | Medium | Low | P0 |
| 3 | Framework & Runtime | Gunicorn+gevent → uvicorn async runtime | High | Medium | P0 |
| 4 | Framework & Runtime | ThreadPoolExecutor → native async/await for I/O | Medium | Medium | P1 |
| 5 | Delivery Infrastructure | Firehose → Kafka standalone module | High | High | P0 |
| 6 | Delivery Infrastructure | Delivery abstraction layer (decouple send interface) | Medium | Medium | P1 |
| 7 | Data Access | RDS standalone module extraction | Medium | High | P0 |
| 8 | Data Access | Async DB driver (psycopg3 async or asyncpg) | Medium | Medium | P1 |
| 9 | Data Access | Connection pooling formalization | Medium | Low | P1 |
| 10 | Data Access | Startup resilience — graceful degradation if RDS unreachable | High | Low | P1 |
| 11 | Observability | Manual OTEL → auto-instrumentation | High | Low | P0 |
| 12 | Observability | Golden Signals instrumentation (p50/p95/p99 latency, error rate, traffic, saturation) | High | Medium | P1 |
| 13 | Observability | Add /ops/* diagnostic endpoints | Medium | Low | P1 |
| 14 | Security | T1_SALT security hash preservation via cnlib | High | Low | P0 |
| 15 | Security | Dependency hash pinning via pip-compile | High | Low | P0 |
| 16 | Security | Non-root container user standardization (containeruser UID 10000) | Medium | Low | P0 |
| 17 | Developer Experience | Test suite creation (unit + integration) | High | High | P0 |
| 18 | Developer Experience | CI/CD pipeline (lint, type check, test, build, deploy) | High | Medium | P1 |
| 19 | Developer Experience | Linting + formatting (ruff) | Medium | Low | P1 |
| 20 | Developer Experience | Type checking (mypy) | Medium | Low | P2 |
| 21 | Dependency Management | requirements.txt → pip-compile with hashes (scripts/lock.sh) | High | Low | P0 |
| 22 | Dependency Management | cnlib vendored symlink → direct COPY in Dockerfile | Medium | Low | P0 |
| 23 | API Design | OpenAPI auto-generation via FastAPI | High | Low | P0 |
| 24 | API Design | Pydantic request/response models | High | Medium | P1 |
| 25 | API Design | API versioning strategy (path prefix readiness) | Low | Low | P2 |
| 26 | Containerization | Dockerfile modernization (Python 3.12-bookworm, HEALTHCHECK, port 8000) | Medium | Low | P0 |
| 27 | Containerization | entrypoint.sh migration to uvicorn startup pattern | Medium | Low | P0 |
| 28 | Containerization | environment-check.sh standardization from template | Medium | Low | P0 |
| 29 | Infrastructure | Helm chart modernization from template (helpers, HTTPRoute, Dapr, KEDA) | Medium | Medium | P1 |
| 30 | Infrastructure | Skaffold for local development | Low | Low | P2 |

## 2. Detailed Opportunity Descriptions

### Opportunity 1 — Flask → FastAPI Migration

- **Current State:** Flask 3.1.1 with synchronous request handling. Routes defined via `Blueprint` and `init_routes()` pattern. Manual exception classes for error responses. No automatic schema validation or API documentation.
- **Target State:** FastAPI application factory using `create_app()` with `asynccontextmanager` lifespan, matching template-repo-python. `APIRouter` for route grouping. Native async request handlers.
- **Rationale:** FastAPI provides automatic OpenAPI documentation, Pydantic-based request validation, native async support, and dependency injection — eliminating multiple manual patterns in the legacy code. This is a non-negotiable rebuild constraint.
- **Dependencies:** Python 3.12 (#2), uvicorn runtime (#3), Pydantic models (#24), OTEL auto-instrumentation (#11).
- **Risk if Skipped:** Cannot meet rebuild requirements. The entire target architecture is built around FastAPI.

### Opportunity 2 — Python 3.10 → 3.12 Upgrade

- **Current State:** Python 3.10-bookworm Docker base image. Missing exception groups, `tomllib`, `TaskGroup`, and the 25%+ performance improvements in 3.11/3.12.
- **Target State:** Python 3.12-bookworm base image matching template-repo-python.
- **Rationale:** Two major versions behind. 3.12 brings significant performance gains, better error messages, and language features that improve code quality. Template standardization requires 3.12.
- **Dependencies:** None — all current dependencies support 3.12.
- **Risk if Skipped:** Fleet divergence from template standard. Missing performance improvements relevant to a high-throughput service. 3.10 EOL approaches (October 2026).

### Opportunity 3 — Gunicorn+gevent → uvicorn Async Runtime

- **Current State:** Gunicorn with 3 gevent workers, 500 connections each, monkey-patching for cooperative multitasking. Configuration: `-w 3 -k gevent --worker-connections=500 --max-requests 100000`.
- **Target State:** uvicorn ASGI server, matching template-repo-python entrypoint pattern. Native async event loop without monkey-patching.
- **Rationale:** gevent monkey-patching introduces subtle bugs and debugging complexity. uvicorn with FastAPI provides true async handling, simpler concurrency model, and better integration with OTEL auto-instrumentation. Template standardization requires uvicorn.
- **Dependencies:** FastAPI migration (#1).
- **Risk if Skipped:** Cannot run FastAPI as ASGI application. gevent monkey-patching conflicts with OTEL auto-instrumentation.

### Opportunity 4 — ThreadPoolExecutor → Native async/await

- **Current State:** `ThreadPoolExecutor` used in `utils.py` for parallel Firehose sends. Blocking thread model for I/O-bound operations within gevent cooperative multitasking.
- **Target State:** Native `async/await` with `asyncio.gather()` for parallel I/O operations (Kafka sends, DB queries). No thread pool needed for I/O concurrency.
- **Rationale:** FastAPI + uvicorn provide a native async event loop. Using `asyncio.gather()` for parallel sends is more efficient, uses fewer resources, and is the idiomatic pattern for async Python I/O.
- **Dependencies:** FastAPI migration (#1), Kafka module (#5).
- **Risk if Skipped:** Functional — ThreadPoolExecutor works under uvicorn. But it wastes OS threads for I/O wait and misses the primary benefit of async migration.

### Opportunity 5 — Firehose → Kafka Standalone Module

- **Current State:** Direct coupling to AWS Kinesis Firehose via `cnlib.firehose.Firehose` throughout `utils.py`. Up to 6 Firehose stream names configured via environment variables (evergreen + legacy × normal + debug channels). `boto3` SDK calls embedded in business logic.
- **Target State:** Standalone Kafka Python module (separate repository, installed as a package). The tvevents service calls a clean send interface; Kafka connection management, serialization, and delivery guarantees are encapsulated in the module.
- **Rationale:** Firehose-to-Kafka migration is one of the three core rebuild constraints. Extracting to a standalone module enables reuse across the service fleet and decouples delivery infrastructure from business logic. Topic configuration replaces stream name environment variables.
- **Dependencies:** Delivery abstraction layer (#6) for clean integration.
- **Risk if Skipped:** Cannot meet rebuild requirements. Firehose replacement is a non-negotiable constraint.

### Opportunity 6 — Delivery Abstraction Layer

- **Current State:** No abstraction — `utils.py` directly calls `cnlib.firehose.Firehose` methods, constructs Firehose-specific payloads, and manages delivery stream routing inline.
- **Target State:** A clean internal interface (e.g., protocol class or abstract base) that the business logic calls. The Kafka module implements this interface. Business logic is unaware of whether delivery happens via Kafka, Firehose, or a test stub.
- **Rationale:** Decouples business logic from delivery mechanism. Makes testing trivial (mock the interface, not boto3). Prevents re-coupling if the delivery backend changes again.
- **Dependencies:** Kafka module (#5).
- **Risk if Skipped:** Business logic becomes directly coupled to Kafka SDK, repeating the same coupling problem that existed with Firehose.

### Opportunity 7 — RDS Standalone Module Extraction

- **Current State:** `dbhelper.py` contains `TvEventsRds` class with direct `psycopg2` connection management, query execution, and blacklist cache initialization. Connection parameters from environment variables. Custom OTEL spans on all DB operations.
- **Target State:** Standalone RDS Python module (separate repository, installed as a package) providing connection management, query execution, and OTEL-instrumented operations. The tvevents service imports and configures it.
- **Rationale:** Core rebuild constraint. Multiple services in the fleet need RDS access — extracting to a shared module eliminates duplication and standardizes connection management, error handling, and observability patterns.
- **Dependencies:** Async DB driver (#8) if async support is included in the module.
- **Risk if Skipped:** Cannot meet rebuild requirements. RDS module extraction is a non-negotiable constraint.

### Opportunity 8 — Async DB Driver

- **Current State:** `psycopg2-binary` — synchronous PostgreSQL adapter. All queries block the calling thread/greenlet.
- **Target State:** `psycopg` (psycopg3) with async support, or `asyncpg`. Non-blocking queries compatible with the async event loop.
- **Rationale:** With FastAPI + uvicorn, synchronous DB calls block the event loop unless offloaded to a thread pool. A native async driver avoids this overhead and provides better throughput under load.
- **Dependencies:** RDS module (#7), FastAPI migration (#1).
- **Risk if Skipped:** Functional — psycopg2 works under uvicorn with `run_in_executor`. But it degrades async benefits and adds latency under concurrent load. For the blacklist cache use case (infrequent reads, small dataset), the impact is limited.

### Opportunity 9 — Connection Pooling Formalization

- **Current State:** `dbhelper.py` creates a new `psycopg2.connect()` call per operation. No explicit connection pool.
- **Target State:** Managed connection pool within the RDS module (via psycopg3 pool or asyncpg pool), initialized at application startup and shared across requests.
- **Rationale:** Connection creation overhead is non-trivial. Pooling reduces latency for cache refresh operations and prevents connection exhaustion under burst traffic (KEDA scales to 500 replicas, each potentially opening connections).
- **Dependencies:** RDS module (#7).
- **Risk if Skipped:** Low for current usage pattern (blacklist cache refreshes infrequently). Medium risk at 500 replicas if multiple pods refresh simultaneously.

### Opportunity 10 — Startup Resilience

- **Current State:** `entrypoint.sh` calls `python -c "from app.dbhelper import TvEventsRds; TvEventsRds().initialize_blacklisted_channel_ids_cache()"` at startup. If RDS is unreachable and no cache file exists, the container crashes with `RuntimeError`.
- **Target State:** Graceful degradation — if RDS is unreachable at startup and no cache file exists, start the service with an empty blacklist (or a stale file cache if available) and schedule a retry. Log a warning, emit a metric, but don't crash.
- **Rationale:** In a 500-replica KEDA deployment, RDS blips during scaling events should not cascade into mass container restarts. The current hard-fail behavior creates a thundering herd problem when RDS recovers.
- **Dependencies:** None.
- **Risk if Skipped:** Mass container failure during RDS connectivity blips. Kubernetes restart loops.

### Opportunity 11 — Manual OTEL → Auto-Instrumentation

- **Current State:** 48+ lines of manual OTEL boilerplate in `app/__init__.py`: TracerProvider, MeterProvider, LoggerProvider, OTLP exporters, resource configuration, and manual instrumentor registration for Flask, psycopg2, botocore, boto3-sqs, requests, urllib3.
- **Target State:** `FastAPIInstrumentor.instrument_app(app)` plus `opentelemetry-bootstrap` in the Dockerfile. Auto-instrumentation handles Flask-equivalent tracing, DB instrumentation, and HTTP client instrumentation with zero boilerplate. Custom application metrics (DB counters, cache counters) retained explicitly.
- **Rationale:** Auto-instrumentation reduces boilerplate from 48 lines to ~3, eliminates version-mismatch bugs between SDK and instrumentors, and automatically picks up new instrumentation as dependencies are added. Template-repo-python uses this pattern.
- **Dependencies:** FastAPI migration (#1).
- **Risk if Skipped:** Functional — manual OTEL works. But it creates maintenance burden, deviates from fleet standard, and risks gaps when new dependencies are added without matching instrumentors.

### Opportunity 12 — Golden Signals Instrumentation

- **Current State:** Custom metrics exist for DB operations and cache operations. No explicit request-level Golden Signals: p50/p95/p99 latency histograms, request rate counters by endpoint, error rate counters by status code, saturation metrics (queue depth, connection pool usage).
- **Target State:** Golden Signals emitted automatically via OTEL auto-instrumentation (request duration, status codes) plus custom saturation metrics (Kafka producer queue depth, connection pool utilization).
- **Rationale:** Golden Signals are the foundation for SLO-based alerting. Without them, SRE teams cannot set meaningful targets or detect degradation before customers are impacted.
- **Dependencies:** OTEL auto-instrumentation (#11) provides most signals. Custom saturation metrics require Kafka module (#5) and RDS module (#7).
- **Risk if Skipped:** No SLO-based monitoring. Alert thresholds remain based on guesswork instead of measured baselines.

### Opportunity 13 — /ops/* Diagnostic Endpoints

- **Current State:** Only `GET /status` returning `{"status": "ok"}`. No diagnostic endpoints for SRE tooling.
- **Target State:** `/ops/health` (liveness), `/ops/ready` (readiness — checks cache state, Kafka connectivity), `/ops/info` (build version, uptime, cache age, replica identity).
- **Rationale:** Kubernetes liveness and readiness probes need distinct endpoints to differentiate "container is alive" from "container is ready to serve traffic." `/ops/info` provides instant diagnostic data without SSH access.
- **Dependencies:** FastAPI migration (#1).
- **Risk if Skipped:** Kubernetes probes use the same `/status` endpoint for both liveness and readiness, potentially routing traffic to unready pods or killing pods that are alive but warming up.

### Opportunity 14 — T1_SALT Security Hash Preservation

- **Current State:** `cnlib.token_hash.security_hash_match` validates request authenticity using a shared salt. Working correctly in production.
- **Target State:** Identical — continue using `cnlib.token_hash.security_hash_match`. The function signature, algorithm, and salt sourcing from environment variables remain unchanged.
- **Rationale:** This is backward-compatible auth that TV device firmware depends on. Any change breaks all deployed devices. This is a "preserve exactly" requirement.
- **Dependencies:** cnlib must remain available (#22).
- **Risk if Skipped:** Not applicable — this must be preserved, not skipped.

### Opportunity 15 — Dependency Hash Pinning

- **Current State:** Flat `requirements.txt` with version pins but no hash verification. Packages could be substituted in a supply chain attack without detection.
- **Target State:** `pip-compile --generate-hashes` workflow via `scripts/lock.sh` matching template-repo-python. `requirements.txt` becomes a generated lockfile with SHA256 hashes for every package.
- **Rationale:** Supply chain security. Hash pinning ensures that the exact binary artifacts used in development are the same ones installed in production. Prevents dependency confusion and substitution attacks.
- **Dependencies:** None.
- **Risk if Skipped:** Supply chain vulnerability. No guarantee that pip installs the same artifacts across environments.

### Opportunity 16 — Non-Root Container User Standardization

- **Current State:** Container runs as `flaskuser` (UID 10000). Non-root but inconsistent naming with fleet standard.
- **Target State:** Container runs as `containeruser` (UID 10000), matching template-repo-python.
- **Rationale:** Fleet consistency. All rebuilt services use the same user naming convention, simplifying security policies and RBAC rules.
- **Dependencies:** Dockerfile modernization (#26).
- **Risk if Skipped:** Functional — any non-root UID is secure. Fleet inconsistency is a minor operational annoyance.

### Opportunity 17 — Test Suite Creation

- **Current State:** No unit tests, no integration tests, no test configuration. `tests/` directory exists but is empty.
- **Target State:** pytest-based test suite covering: request validation, security hash verification, event type classification, channel obfuscation, cache behavior (file read/write, fallback chain), delivery interface mocking, /ops endpoint responses, error paths. Coverage target ≥80%.
- **Rationale:** Zero test coverage is the single biggest risk in the rebuild. Without tests, there is no way to verify that the migrated business logic behaves identically to the legacy implementation. Tests also enable safe future refactoring.
- **Dependencies:** FastAPI migration (#1) — test the new code, not the old.
- **Risk if Skipped:** Silent regressions in business logic. No confidence that the rebuild is functionally equivalent. Every future change is a gamble.

### Opportunity 18 — CI/CD Pipeline

- **Current State:** No CI/CD pipeline visible in the repository. Container builds are referenced in scope but no GitHub Actions workflow exists.
- **Target State:** GitHub Actions workflow: lint (ruff) → type check (mypy) → test (pytest with coverage) → build (Docker) → push (container registry) → deploy (Helm/ArgoCD).
- **Rationale:** Without CI/CD, code quality gates don't exist. Developers can merge untested, unlinted code directly. The template standard requires automated quality gates.
- **Dependencies:** Test suite (#17), linting (#19).
- **Risk if Skipped:** No automated quality enforcement. Manual deployments are error-prone and slow.

### Opportunity 19 — Linting + Formatting (ruff)

- **Current State:** No linter or formatter configured. Code style is maintained by convention only.
- **Target State:** `ruff` for linting and formatting. Configuration in `pyproject.toml`. Pre-commit hook and CI gate.
- **Rationale:** Automated style enforcement eliminates code review friction on formatting and catches common errors (unused imports, undefined variables, unreachable code) before they reach review.
- **Dependencies:** None.
- **Risk if Skipped:** Inconsistent code style. Common bugs slip through review. Minor — but compounds over time.

### Opportunity 20 — Type Checking (mypy)

- **Current State:** No type annotations beyond what Python 3.10 infers. No mypy configuration.
- **Target State:** Type annotations on public interfaces. `mypy` in strict mode for new code. Configuration in `pyproject.toml`.
- **Rationale:** Type annotations provide documentation and catch type errors at development time. Pydantic models (#24) generate type-safe interfaces automatically, making mypy especially valuable.
- **Dependencies:** Pydantic models (#24) — required for full benefit.
- **Risk if Skipped:** Type errors caught at runtime instead of development time. Lower — Python is dynamically typed by design, and the team may not have mypy experience.

### Opportunity 21 — pip-compile with Hashes

- **Current State:** Manual `requirements.txt` with pinned versions, no hashes, no lockfile workflow.
- **Target State:** `scripts/lock.sh` running `pip-compile --generate-hashes` from `requirements.in` (hand-edited top-level deps) to `requirements.txt` (generated lockfile with hashes). Exactly matches template-repo-python.
- **Rationale:** Reproducible builds. Developers edit `requirements.in` with top-level dependencies; `lock.sh` resolves the full dependency tree with pinned versions and hashes. Eliminates "works on my machine" dependency drift.
- **Dependencies:** None.
- **Risk if Skipped:** Non-reproducible builds. Dependency drift between environments. Supply chain vulnerability (see #15).

### Opportunity 22 — cnlib Vendoring Cleanup

- **Current State:** `cnlib` is vendored via a symlink (`cnlib -> cntools_py3/cnlib`). The symlink breaks during some Docker builds and CI pipelines.
- **Target State:** Direct `COPY ./cntools_py3/cnlib ./cnlib` in Dockerfile (matching template-repo-python). No symlink. cnlib installed via `setup.py install` during image build. Three modules used: `token_hash.security_hash_match` (preserved), `log` (preserved), `firehose.Firehose` (dropped — replaced by Kafka module).
- **Rationale:** Symlinks are fragile. The template-repo-python already solved this with a direct COPY. Following the same pattern eliminates a class of build failures.
- **Dependencies:** None.
- **Risk if Skipped:** Intermittent build failures. Developer confusion during local setup.

### Opportunity 23 — OpenAPI Auto-Generation

- **Current State:** No API documentation. Flask does not auto-generate OpenAPI specs.
- **Target State:** FastAPI auto-generates an OpenAPI 3.1 spec at `/docs` (Swagger UI) and `/openapi.json`. Endpoint descriptions, request/response schemas, and error responses are all documented automatically from code.
- **Rationale:** Free with FastAPI migration — requires zero additional effort. Consumers get interactive API documentation. Integration testing can validate against the spec.
- **Dependencies:** FastAPI migration (#1), Pydantic models (#24) for schema richness.
- **Risk if Skipped:** Not possible to skip if FastAPI is adopted — it's automatic.

### Opportunity 24 — Pydantic Request/Response Models

- **Current State:** Request validation is manual string checking in `utils.py` — `if 'tvid' not in request.args`, `if 'h' not in request.args`, etc. No typed response models. Error responses are ad-hoc JSON.
- **Target State:** Pydantic `BaseModel` classes for request parameters (query params, body payload) and response shapes. FastAPI validates automatically and returns 422 with structured error details on invalid input.
- **Rationale:** Eliminates manual validation code. Provides type safety, auto-documentation, and consistent error responses. Pydantic validation is faster than manual checking and catches edge cases (type coercion, missing fields, extra fields).
- **Dependencies:** FastAPI migration (#1).
- **Risk if Skipped:** Manual validation code must be rewritten instead of replaced. Inconsistent error responses. Missing schema documentation in OpenAPI spec.

### Opportunity 25 — API Versioning Strategy

- **Current State:** `POST /` as the root endpoint. No version prefix. Adding versioning later requires a breaking change or redirect.
- **Target State:** Preserve `POST /` for backward compatibility (TV devices cannot be updated en masse). Document a versioning strategy (e.g., `/v2/events`) for future consumers, but do not implement it in this rebuild.
- **Rationale:** TV firmware cannot be updated to use new paths. The current contract must be preserved exactly. Versioning readiness is documentation, not code.
- **Dependencies:** None.
- **Risk if Skipped:** Low — versioning is a future concern. Document the constraint for the next team.

### Opportunity 26 — Dockerfile Modernization

- **Current State:** Python 3.10-bookworm with SHA256 pinning. Non-root `flaskuser`. No `HEALTHCHECK` directive. Port 8000. CVE patches inline.
- **Target State:** Python 3.12-bookworm. Non-root `containeruser` (UID 10000). `HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -fs http://localhost:8000/status || exit 1`. `opentelemetry-bootstrap` run during build. Matching template-repo-python structure.
- **Rationale:** Template standardization. The HEALTHCHECK provides Docker-level health monitoring independent of Kubernetes probes. Python 3.12 base brings performance and security improvements.
- **Dependencies:** Python 3.12 (#2).
- **Risk if Skipped:** Fleet inconsistency. Missing Docker-level health checks. Older Python base.

### Opportunity 27 — entrypoint.sh Migration to uvicorn

- **Current State:** `entrypoint.sh` sources `environment-check.sh`, creates AWS config, configures OTEL headers, initializes blacklist cache, and starts Gunicorn with gevent workers.
- **Target State:** Same structure but replaces Gunicorn startup with uvicorn: `exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ...`. Cache initialization preserved. AWS config creation preserved. OTEL configuration preserved. Matching template-repo-python entrypoint pattern.
- **Rationale:** Required for FastAPI ASGI runtime. The entrypoint structure is sound; only the server command changes.
- **Dependencies:** FastAPI migration (#1), uvicorn runtime (#3).
- **Risk if Skipped:** Cannot run the FastAPI application.

### Opportunity 28 — environment-check.sh Standardization

- **Current State:** Thorough variable validation covering 6 groups (rds_vars, firehose_vars, acr_data_msk_vars, app_vars, always_required, otel_nr_vars) with `TEST_CONTAINER` bypass.
- **Target State:** Standardized structure matching template-repo-python. Variable groups updated: drop firehose_vars, update for Kafka vars, retain rds_vars and app_vars. Keep `TEST_CONTAINER` bypass.
- **Rationale:** Fleet consistency. The legacy environment-check.sh is comprehensive but uses a different structure than the template. Standardizing simplifies operational playbooks.
- **Dependencies:** Kafka module (#5) — new environment variables for Kafka.
- **Risk if Skipped:** Operational inconsistency. Different variable validation patterns across services.

### Opportunity 29 — Helm Chart Modernization

- **Current State:** Helm charts with values.yaml for deployment, service, and KEDA configuration.
- **Target State:** Helm charts matching template-repo-python: advanced template helpers (`_helpers.tpl`), HTTPRoute resources (Gateway API), Dapr component definitions, KEDA ScaledObject, secrets management, configmaps. Full values.yaml with documented configuration.
- **Rationale:** Fleet standardization. The template Helm charts include patterns for Gateway API routing, Dapr integration, and standardized labeling that all rebuilt services should share.
- **Dependencies:** None — Helm charts are independent of application code.
- **Risk if Skipped:** Manual Helm chart maintenance diverges from fleet patterns. Missing Gateway API, Dapr, and standardized KEDA configuration.

### Opportunity 30 — Skaffold for Local Development

- **Current State:** No local development tooling. Developers rely on direct VPN access to development RDS instance.
- **Target State:** `skaffold.yaml` for local Kubernetes development (build + deploy cycle), matching template-repo-python.
- **Rationale:** Fast local iteration. Skaffold automates build-push-deploy during development, reducing the feedback loop from minutes to seconds.
- **Dependencies:** Helm chart modernization (#29).
- **Risk if Skipped:** Slower local development. Developers continue manual Docker builds. Low impact — most development can use `uvicorn --reload` without Kubernetes.

## 3. Prioritized Implementation Order

The following sequence respects dependencies between opportunities and groups work into logical phases.

### Phase 0 — Foundation (No Application Code Yet)

These items establish the project skeleton before any business logic is ported.

| Order | Opportunity | Rationale |
|---|---|---|
| 1 | #2 — Python 3.12 | Base image for everything else |
| 2 | #21 — pip-compile with hashes | Dependency management before adding deps |
| 3 | #22 — cnlib vendoring cleanup | Clean dependency before building on it |
| 4 | #26 — Dockerfile modernization | Container foundation |
| 5 | #28 — environment-check.sh | Startup variable validation |
| 6 | #27 — entrypoint.sh → uvicorn | Startup command |
| 7 | #1 — FastAPI app factory | Application skeleton (create_app, lifespan, router) |
| 8 | #3 — uvicorn runtime | App can start and serve requests |
| 9 | #11 — OTEL auto-instrumentation | Observability from first request |
| 10 | #15 — Hash pinning | Secure from first dependency |

### Phase 1 — Core Business Logic Migration

Port existing functionality into the new skeleton.

| Order | Opportunity | Rationale |
|---|---|---|
| 11 | #14 — T1_SALT hash preservation | Auth must work before business logic |
| 12 | #24 — Pydantic models | Request validation foundation |
| 13 | #23 — OpenAPI auto-generation | Free with FastAPI + Pydantic — no separate effort |
| 14 | #7 — RDS module extraction | Data access before cache logic |
| 15 | #10 — Startup resilience | Cache init with graceful degradation |
| 16 | #5 — Kafka standalone module | Delivery mechanism before send logic |
| 17 | #6 — Delivery abstraction layer | Clean interface for business logic to use |
| 18 | #4 — async/await for I/O | Async Kafka sends, async DB queries |

### Phase 2 — Quality & Observability

Build confidence and operational visibility.

| Order | Opportunity | Rationale |
|---|---|---|
| 19 | #17 — Test suite | Validate migrated logic |
| 20 | #13 — /ops/* endpoints | SRE diagnostic tooling |
| 21 | #12 — Golden Signals | SLO-ready metrics |
| 22 | #19 — Linting (ruff) | Code quality enforcement |
| 23 | #9 — Connection pooling | Performance under load |
| 24 | #16 — containeruser standardization | Fleet consistency |

### Phase 3 — Polish & Infrastructure

Final standardization and operational tooling.

| Order | Opportunity | Rationale |
|---|---|---|
| 25 | #8 — Async DB driver | Performance optimization |
| 26 | #18 — CI/CD pipeline | Automated quality gates |
| 27 | #29 — Helm chart modernization | Deployment standardization |
| 28 | #25 — API versioning strategy | Documentation only |
| 29 | #20 — Type checking (mypy) | Code quality improvement |
| 30 | #30 — Skaffold | Developer experience enhancement |

## 4. Quick Wins

Low effort opportunities with High or Medium impact that can be completed early in the rebuild. These provide immediate value with minimal investment.

| # | Opportunity | Effort | Impact | Why It's Quick |
|---|---|---|---|---|
| #2 | Python 3.12 upgrade | Low | Medium | Change one line in Dockerfile (`FROM python:3.12-bookworm`) |
| #11 | OTEL auto-instrumentation | Low | High | Replace 48 lines of manual setup with `FastAPIInstrumentor.instrument_app(app)` + `opentelemetry-bootstrap` |
| #15 | Hash pinning | Low | High | Copy `scripts/lock.sh` from template-repo-python, run once |
| #21 | pip-compile workflow | Low | High | Same as #15 — one script, one run |
| #22 | cnlib symlink cleanup | Low | Medium | Change `COPY` directive in Dockerfile, delete symlink |
| #23 | OpenAPI auto-generation | Low | High | Automatic with FastAPI — zero code required |
| #16 | containeruser standardization | Low | Medium | Rename user in Dockerfile |
| #10 | Startup resilience | Low | High | Wrap cache init in try/except, schedule retry |
| #13 | /ops/* endpoints | Low | Medium | Three simple FastAPI route handlers |
| #19 | Linting (ruff) | Low | Medium | Add `[tool.ruff]` to pyproject.toml, run `ruff check --fix` |

## 5. Risk Registry

Modernization opportunities that introduce new risk.

| Risk | Source Opportunity | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| **Async behavior divergence** | #1 (FastAPI), #3 (uvicorn), #4 (async I/O) | High | Medium | Comprehensive test suite (#17) comparing output parity between legacy sync and new async paths. Load testing to verify behavior under concurrency. |
| **Kafka delivery parity** | #5 (Kafka module) | High | Medium | Side-by-side validation period: run both Firehose and Kafka in parallel, compare message counts and payload content. Automated reconciliation checks. |
| **RDS module extraction breaks cache** | #7 (RDS module) | Medium | Low | The 3-tier cache logic is well-understood and the dataset is small. Unit tests for all cache paths (memory hit, file hit, DB hit, DB miss). Integration test with a real PostgreSQL instance. |
| **OTEL metric loss during migration** | #11 (auto-instrumentation) | Medium | Medium | Inventory all custom metrics before migration. Auto-instrumentation covers request-level metrics; verify custom DB and cache counters are re-registered explicitly. Compare New Relic dashboards before/after. |
| **Async DB driver compatibility** | #8 (async driver) | Medium | Low | psycopg3 is mature and backward-compatible with psycopg2 query syntax. However, connection lifecycle differs. Test all query patterns. Fallback: keep psycopg2 with `run_in_executor`. |
| **cnlib compatibility with Python 3.12** | #2 (Python upgrade), #22 (cnlib cleanup) | Medium | Low | cnlib is a simple Python package. Test `security_hash_match` and `log` functions on 3.12 before committing. If incompatible, vendor the specific functions directly. |
| **KEDA scaling behavior change** | #3 (uvicorn) | Medium | Low | uvicorn's concurrency model differs from Gunicorn+gevent. The same KEDA CPU/memory triggers may scale differently. Load test with production-representative traffic and tune KEDA thresholds. |
| **Backward compatibility break** | #24 (Pydantic models) | Medium | Low | Pydantic may reject requests that Flask silently accepted (e.g., extra fields, type mismatches). Test with captured production request samples. Configure Pydantic to `model_config = ConfigDict(extra="allow")` if needed. |
| **Helm chart migration disrupts deployments** | #29 (Helm modernization) | Medium | Medium | Deploy to a staging environment first. Use `helm diff` to compare rendered templates before and after. Ensure rollback plan is tested. |
| **Zero-to-test coverage confidence** | #17 (Test suite) | Low | High | With no existing tests as a baseline, the new test suite defines correctness from scratch. Mitigate by testing against captured production request/response pairs where possible. |
