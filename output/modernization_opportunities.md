# Modernization Opportunities — evergreen-tvevents

> Every opportunity below traces to a specific pain point from scope.md or a finding from the legacy assessment. No hypothetical improvements.

---

## Opportunity 1: Remove cntools_py3/cnlib Dependency

**Pain Point:** scope.md #1: "cntools_py3/cnlib dependency — bundles unused libs, breaks CI, coupling point." Legacy assessment: "cnlib dependency creates tight coupling to an external shared library for core functionality." Code & Dependency Health rated Poor.

**Current State:** The application depends on `cntools_py3/cnlib` — a git submodule from `git@github.com:CognitiveNetworks/cntools_py3.git` — for three functions: `firehose.Firehose` (Kinesis delivery), `token_hash.security_hash_match` (HMAC validation), and `log.getLogger` (logging). The submodule bundles Redis, memcached, ZeroMQ, MySQL, Consul, PagerDuty, and dozens of other libraries the application never uses. CI requires explicit `submodules: true` checkout or builds fail. The Dockerfile copies cnlib and runs `setup.py install` — a legacy packaging pattern. The submodule is frequently out of sync with its upstream. Three functions from a massive shared library.

**Target State:** Zero cnlib dependency. Each consumed function is replaced with a standalone implementation in the new codebase:
- `token_hash.security_hash_match` → local HMAC validation module using `hmac.compare_digest()` for constant-time comparison (addressing the security concern flagged in the legacy assessment).
- `firehose.Firehose` → replaced entirely by Kafka producer (see Opportunity 2).
- `log.getLogger` → standard Python `logging` module with OTEL-correlated structured JSON output.

No git submodule. No `setup.py install` in Docker build. No transitive dependency on Redis, memcached, ZeroMQ, MySQL, Consul, or PagerDuty libraries.

**Migration Path:**
1. Audit the three cnlib call sites in the legacy codebase (`utils.py` for firehose and token_hash, `__init__.py` for log).
2. Implement standalone HMAC validation using `hashlib` and `hmac` from the Python standard library, with `hmac.compare_digest()` for constant-time comparison.
3. Replace `cnlib.log.getLogger` with standard `logging.getLogger` configured for structured JSON output with OTEL trace/span correlation.
4. Kafka producer replaces Firehose delivery (Opportunity 2 handles this).
5. Validate HMAC behavior against legacy by testing with production-like payloads (real MAC address formats, real salt patterns).

**What Could Go Wrong:**
- `security_hash_match` may have undocumented behavior beyond simple HMAC comparison (salt preprocessing, encoding normalization, hash algorithm choice). The cnlib submodule is empty in the clone — the exact implementation must be reverse-engineered from test cases and integration testing against the live service.
- If `log.getLogger` injects custom log formatting or routing beyond standard Python logging, log consumers may see format changes.

**Impact:** Critical — unblocks independent deployment, eliminates the primary CI failure mode, and removes 80+ transitive dependencies in a single change.

---

## Opportunity 2: Replace AWS Kinesis Data Firehose with Apache Kafka

**Pain Point:** scope.md #2: "Firehose → Kafka migration required by org." Legacy assessment: "Firehose delivery is AWS-specific (via cnlib/boto3). Medium lock-in."

**Current State:** Processed TV events are delivered to AWS Kinesis Data Firehose via `cnlib.firehose.Firehose`, which wraps boto3 `put_record` calls. Delivery targets are configured through environment variables: `EVERGREEN_FIREHOSE_NAME`, `LEGACY_FIREHOSE_NAME`, and debug variants (`DEBUG_EVERGREEN_FIREHOSE_NAME`, `DEBUG_LEGACY_FIREHOSE_NAME`). Complex env-var-driven routing logic determines which combination of streams receives each event (`SEND_LEGACY`, `SEND_EVERGREEN`, `SEND_DEBUG_LEGACY`, `SEND_DEBUG_EVERGREEN`). The data lands in S3 buckets (`cn-tvevents/<ZOO>/tvevents/`) consumed by downstream analytics pipelines. The output JSON format — a flattened structure with specific key naming conventions — is an implicit contract with those consumers.

**Target State:** Kafka producer using `confluent-kafka` sends processed events to Kafka topics. Topic names replace Firehose stream names. The output JSON format is preserved byte-for-byte — downstream consumers see the same flattened JSON schema. The complex legacy/evergreen/debug routing logic is simplified to topic-based routing. `boto3` is removed from the dependency tree entirely (it was used only for Firehose via cnlib).

**Migration Path:**
1. Define Kafka topic schema matching the existing flattened JSON output format. Document as a versioned contract.
2. Implement Kafka producer service layer with `confluent-kafka`, including: connection pooling, delivery callbacks, retry with exponential backoff, and dead-letter topic for failed messages.
3. Map legacy Firehose routing logic to Kafka topic routing — each `*_FIREHOSE_NAME` env var maps to a Kafka topic config.
4. Run parallel delivery during migration: new service writes to Kafka, bridge consumer writes Kafka messages to S3 in the same path structure so downstream pipelines are unaffected.
5. Validate output JSON byte-for-byte compatibility with legacy Firehose records.
6. Cut over downstream consumers from S3 (Firehose-delivered) to S3 (Kafka-delivered) or direct Kafka consumption.

**What Could Go Wrong:**
- **Output format drift.** The flattened JSON structure is an implicit contract. Any difference in key ordering, null handling, or numeric formatting breaks downstream pipelines. Mitigation: golden-file tests comparing new output against captured legacy output for each event type.
- **Delivery semantics.** Firehose provides at-least-once delivery with automatic retry. Kafka producer must be configured for equivalent guarantees (`acks=all`, `enable.idempotence=true`).
- **Throughput at scale.** Production runs 300–500 pods. Kafka producer connection management and partition assignment at this scale needs load testing.
- **Downstream consumer readiness.** Unknown consumers read from S3 buckets. The parallel-run bridge must maintain identical S3 path structure during transition.

**Impact:** Critical — organizational mandate to migrate to Kafka. Removes AWS-specific data delivery coupling and eliminates boto3 dependency.

---

## Opportunity 3: Extract Standalone Redis Module

**Pain Point:** scope.md #3: "No standalone Redis module — other services need reusable Redis client." scope.md Target State: "Produce a standalone Redis Python module (`rebuilder-redis-module`) that can be used independently."

**Current State:** The application uses Redis only through cnlib's wrapper. There is no standalone, reusable Redis client that other services can consume. cnlib bundles `redis==6.0.0` as a transitive dependency, but the wrapper adds connection logic, module-level side effects (connections established at import time), and custom error handling that is tightly coupled to cnlib internals. Other services rebuilding off cnlib face the same problem: no clean Redis abstraction to reuse.

**Target State:** A standalone Python package — `rebuilder-redis-module` — published to an internal package registry. The module provides:
- Connection management with pooling and health checks.
- Async support (via `redis.asyncio`).
- Configurable retry with exponential backoff and jitter.
- Clean shutdown (explicit pool closure, not garbage collection).
- OTEL-instrumented operations (traces on get/set/delete, latency histograms).
- No module-level side effects — connections created explicitly, not at import time.
- Used by evergreen-tvevents for blacklist cache (replacing file-based cache — see Opportunity 4) and available for any other service.

**Migration Path:**
1. Design the module API: `RedisClient` class with constructor injection of connection parameters, async context manager support, and health check method.
2. Implement in a separate repository (`rebuilder-redis-module`) with its own CI, tests, and versioned releases.
3. Publish to internal PyPI registry.
4. Consume from `rebuilder-evergreen-tvevents` as a pinned dependency.
5. Document usage patterns and configuration for other teams adopting the module.

**What Could Go Wrong:**
- **API design mismatch.** If the module API doesn't anticipate the access patterns of other services (e.g., LUA scripts, pipeline operations, pub/sub), it will need breaking changes early. Mitigation: survey other teams' Redis usage patterns before finalizing the API.
- **Version coordination.** Multiple services depending on a shared module creates a versioning coordination point. Mitigation: semantic versioning with strict backward compatibility guarantees.

**Impact:** High — enables clean Redis access for this service and produces a reusable artifact for the broader platform.

---

## Opportunity 4: Replace File-Based Cache with Redis

**Pain Point:** scope.md #4: "File-based caching is fragile." Legacy assessment: "File-based cache for blacklisted channel IDs — fragile, not shared across pods, lost on pod restarts." Data Health: "In-memory cache is per-process, never explicitly refreshed."

**Current State:** Blacklisted channel IDs are cached in two layers:
1. **In-memory:** A module-level variable `_blacklisted_channel_ids` populated on first read from RDS. Never refreshed — the process must restart to pick up changes. Each Gunicorn worker has its own copy.
2. **File-based:** Written to `/tmp/.blacklisted_channel_ids_cache`. Read on startup if RDS is unreachable. Fragile: not shared across pods (each pod's `/tmp` is ephemeral), lost on pod restart, filesystem write failures silently degrade to no cache.

Additionally, RDS connections have no pooling — `dbhelper.py` opens a new PostgreSQL connection per query via `psycopg2.connect()` and closes it immediately. At 300–500 pods, this means potentially hundreds of short-lived connections hitting RDS simultaneously on cache refresh.

**Target State:** Blacklist cache stored in Redis (via `rebuilder-redis-module`):
- Shared across all pods — a single source of truth.
- TTL-based expiry with configurable refresh interval.
- Graceful degradation: if Redis is unreachable, fall back to in-memory cache (last known good set), not to filesystem.
- RDS queries use connection pooling (`asyncpg` pool or `psycopg` connection pool) — bounded connection count, reused connections.
- Cache refresh is explicit: a background task queries RDS on a schedule and writes to Redis. Individual request handlers read from Redis only.

**Migration Path:**
1. Implement Redis-backed cache using `rebuilder-redis-module` — store blacklisted channel IDs as a Redis set with TTL.
2. Implement background refresh task: query RDS periodically, write result to Redis, update in-memory fallback.
3. Replace `dbhelper.py` direct connections with a connection pool (bounded to a configurable max, e.g., 5 connections per pod).
4. Remove file-based cache code (`/tmp/.blacklisted_channel_ids_cache` read/write logic).
5. Load test cache refresh at production pod count to verify Redis and RDS connection behavior.

**What Could Go Wrong:**
- **Redis unavailability during cold start.** If Redis is down and there is no file cache, the service has no blacklist data. Mitigation: in-memory fallback with a health check that reports degraded state (not healthy) when operating without fresh cache data.
- **Thundering herd.** If all 300–500 pods refresh cache simultaneously (e.g., after a Redis flush), RDS gets hit with hundreds of concurrent queries. Mitigation: jittered refresh intervals per pod, and Redis-based distributed lock so only one pod refreshes at a time.
- **Stale data window.** TTL-based expiry means blacklist changes take up to one TTL interval to propagate. Document the expected staleness window and confirm it's acceptable with the data engineering team.

**Impact:** High — eliminates fragile filesystem dependency, enables shared cache across pods, and fixes the per-request RDS connection anti-pattern.

---

## Opportunity 5: Upgrade Python 3.10 to 3.12+

**Pain Point:** scope.md #5: "Python 3.10 behind LTS." Legacy assessment: "Python 3.10: One major version behind current LTS (3.12)."

**Current State:** The application runs Python 3.10 on a `python:3.10-bookworm` base image (full Debian, not slim). Python 3.10 reached end of security fixes in October 2026. The Dockerfile pins the base image by SHA digest, which is good practice, but the underlying Python version is approaching EOL. `mypy` is configured with `ignore_missing_imports = true` — no meaningful type checking. No type annotations in application code.

**Target State:** Python 3.12+ with:
- `python:3.12-slim-bookworm` base image (smaller attack surface, fewer unnecessary packages).
- Full type annotations on all functions, leveraging Python 3.12 syntax improvements (e.g., `type` statement, `TypeVar` defaults).
- `mypy --strict` passing in CI (not `ignore_missing_imports = true`).
- Access to performance improvements: Python 3.12 delivers 10–25% faster execution via specializing adaptive interpreter.
- `ExceptionGroup` and `TaskGroup` support for structured concurrency in async code.

**Migration Path:**
1. Update base image in Dockerfile from `python:3.10-bookworm` to `python:3.12-slim-bookworm`.
2. Resolve any Python 3.11/3.12 deprecation warnings or breaking changes (e.g., `asyncio` policy changes, `importlib` changes).
3. Add type annotations to all modules. Configure `mypy --strict`.
4. Update CI to test against Python 3.12.
5. Update `.python-version` file.

**What Could Go Wrong:**
- **C extension compatibility.** `psycopg2-binary` and `confluent-kafka` (new dependency) must have wheels available for Python 3.12. Both do as of current releases.
- **Slim image missing build dependencies.** The legacy Dockerfile installs several apt packages for CVE remediation. Slim image may lack these. Mitigation: multi-stage build — build dependencies in a builder stage, copy only runtime artifacts to slim.
- **Behavioral changes.** Python 3.12 changed some default behaviors (e.g., `hashlib` algorithm availability, `ssl` module defaults). Test suite must cover these paths.

**Impact:** Medium — addresses security (EOL timeline), performance, and developer experience (type safety). Low risk because the application logic is straightforward and not tied to CPython internals.

---

## Opportunity 6: Migrate Flask to FastAPI

**Pain Point:** scope.md #6: "Flask instead of async framework." scope.md #7: "No OpenAPI spec." Legacy assessment: API Surface Health rated Poor. "No OpenAPI specification. No automatic documentation. No API versioning. No typed response models."

**Current State:** Flask 3.1.1 with Gunicorn + gevent workers. Gevent monkey-patches the standard library for concurrency — implicit cooperative multitasking that is hard to reason about and debug. Two endpoints: POST `/` and GET `/status`. No OpenAPI spec. No Pydantic models. No typed responses — returns plain strings or `jsonify()` dicts. Error handling wraps all exceptions into `TvEventsCatchallException` with a blanket 400 status, losing error specificity. The POST endpoint mixes query parameters (`tvid`, `event_type`) and JSON body, with no schema validation at the framework level. No request size limits at the app level. No versioning.

**Target State:** FastAPI with uvicorn + uvloop:
- Native async/await — no monkey-patching, explicit concurrency model.
- Pydantic request models with validation for all input (query params, JSON body, headers).
- Pydantic response models with typed fields and examples.
- Automatic OpenAPI 3.1 spec generation from route definitions and models.
- API versioning: `/v1/events` POST replaces `/`.
- `/health` with dependency checking replaces `/status`.
- Structured error responses with error codes, not blanket 400s.
- Built-in dependency injection for services (Kafka producer, Redis client, RDS pool).
- Request size limits via middleware.

**Migration Path:**
1. Define Pydantic models for: event request payload (per event type), event response, health response, error response.
2. Port `routes.py` POST handler to FastAPI route with Pydantic validation replacing manual `utils.py` checks.
3. Port event type validation from `event_type.py` class hierarchy to Pydantic discriminated unions or preserved polymorphic pattern with typed inputs/outputs.
4. Replace Gunicorn + gevent with uvicorn + uvloop.
5. Implement FastAPI dependency injection for Kafka producer, Redis client, and RDS connection pool.
6. Generate OpenAPI spec and validate against legacy endpoint behavior.
7. Verify all existing test cases pass against the new route handlers.

**What Could Go Wrong:**
- **Behavioral differences in parameter binding.** Flask's `request.args` and `request.get_json()` have specific error handling (e.g., malformed JSON returns None). FastAPI's Pydantic validation rejects malformed input with 422. TV firmware sending borderline-valid payloads may start getting rejected. Mitigation: capture a corpus of production payloads and validate the new service accepts all of them.
- **Gevent implicit concurrency vs async explicit concurrency.** Code that relied on gevent's cooperative scheduling (e.g., blocking I/O that gevent silently makes async) must be explicitly awaited in FastAPI. All I/O calls (RDS, Redis, Kafka) need async implementations.
- **OpenAPI spec becomes a contract.** Once published, any change to the spec is a breaking change for consumers who code-generate against it.

**Impact:** High — resolves three pain points simultaneously (no async, no OpenAPI, no typed responses) and enables modern Python development patterns.

---

## Opportunity 7: Remove Embedded PagerDuty

**Pain Point:** scope.md #8: "Embedded PagerDuty." Legacy assessment: "pygerduty dependency for alerting embedded in the application." "PagerDuty is embedded via pygerduty rather than handled externally."

**Current State:** The application includes `pygerduty==0.38.3` as a runtime dependency and references PagerDuty service ID `PSV1WEB`. Alerting logic is embedded in the application — the service directly creates PagerDuty incidents. This couples the application to a specific alerting vendor, adds an unused dependency to the runtime image, and means alerting configuration changes require application redeployment.

**Target State:** Zero PagerDuty dependency in the application. Alerting becomes an infrastructure concern:
- Application emits OTEL metrics and structured logs.
- OTEL Collector exports to the monitoring backend.
- Alert rules defined in the monitoring platform (e.g., Datadog, New Relic, or PagerDuty's native OTEL integration) trigger PagerDuty incidents based on SLO violations, error rate thresholds, or saturation alerts.
- Changing alert thresholds or routing requires no application deployment.
- `pygerduty` removed from `requirements.txt`.

**Migration Path:**
1. Identify all PagerDuty trigger points in the legacy codebase — map each to an equivalent OTEL metric or log event.
2. Ensure the new service emits those metrics/events via OTEL.
3. Configure alert rules in the external monitoring platform to trigger PagerDuty for the same conditions.
4. Remove `pygerduty` from dependencies.
5. Validate alerts fire correctly during parallel run by injecting test failures.

**What Could Go Wrong:**
- **Alert gap during transition.** If legacy PagerDuty triggers are removed before external alert rules are configured, incidents go undetected. Mitigation: configure external alerts first, validate they fire, then remove embedded PagerDuty.
- **Loss of alert context.** Embedded PagerDuty calls may include application-specific context (stack traces, payload excerpts) that generic OTEL-based alerts don't. Mitigation: ensure structured log events carry equivalent diagnostic context and are linked to alerts via trace IDs.

**Impact:** Medium — removes a vendor-specific runtime dependency and aligns alerting with the OTEL-based observability strategy. Low technical risk.

---

## Opportunity 8: Add SRE Diagnostic and Remediation Endpoints

**Pain Point:** scope.md #9: "No SRE diagnostic endpoints." Legacy assessment: "/status returns 'OK' regardless of whether RDS or Firehose are reachable. No graceful drain mechanism."

**Current State:** The only operational endpoint is `GET /status`, which returns the plain string "OK" with a 200 status code. It does not check whether PostgreSQL (RDS), Firehose, or any other dependency is reachable. Kubernetes liveness and readiness probes both hit `/status`, meaning a pod reports healthy even when its dependencies are down. There is no graceful drain mechanism — no way to tell a pod to stop accepting traffic before shutdown. No endpoint to inspect configuration, dependency health, error rates, cache state, or circuit breaker status at runtime.

**Target State:** Full `/ops/*` endpoint suite:
- `/health` — dependency-checking health endpoint. Returns 200 only if RDS, Redis, and Kafka are reachable. Returns 503 with a JSON body listing which dependencies are down. Used for Kubernetes readiness probes.
- `/ops/status` — service metadata: version, uptime, environment, pod identity.
- `/ops/health` — deep health check with per-dependency status and latency.
- `/ops/metrics` — application metrics snapshot (Golden Signals, cache hit rates, Kafka producer stats).
- `/ops/config` — non-sensitive runtime configuration (redacts secrets).
- `/ops/dependencies` — dependency inventory with connection pool stats, circuit breaker states, and last-seen latency.
- `/ops/errors` — recent error log entries, grouped by type, with trace IDs for correlation.
- `/ops/drain` — sets a drain flag causing `/health` to return 503, allowing load balancers to stop routing traffic before graceful shutdown.
- `/ops/cache/flush` — manually flush the blacklist cache (triggers re-fetch from RDS).
- `/ops/loglevel` — change log verbosity at runtime without redeployment.
- All `/ops/*` endpoints are internal-only — not exposed via Kong API Gateway.

**Migration Path:**
1. Implement `/health` first — this is the Kubernetes readiness probe target. RDS ping, Redis ping, Kafka metadata request.
2. Implement `/ops/drain` — required for zero-downtime deployments. Wire into SIGTERM handler.
3. Implement remaining `/ops/*` endpoints incrementally.
4. Update Helm/Terraform to configure Kubernetes probes: liveness → `/ops/status`, readiness → `/health`.
5. Document each endpoint's response schema in the OpenAPI spec.

**What Could Go Wrong:**
- **Sensitive data exposure.** `/ops/config` and `/ops/errors` could leak secrets or PII if not carefully filtered. Mitigation: explicit allowlists for config keys, redaction of any value matching secret patterns.
- **Drain flag not reset.** If `/ops/drain` is called but the pod isn't actually terminated, it stays in a drained state indefinitely. Mitigation: drain flag auto-resets after a configurable timeout, and `/ops/status` shows drain state.
- **Health check cascading failure.** If `/health` makes synchronous calls to all dependencies and one is slow, health checks time out and Kubernetes kills the pod. Mitigation: per-dependency timeouts (e.g., 2s each) and cached health state with a short TTL.

**Impact:** High — transforms operational visibility from "is the process alive" to "is the service functioning correctly." Prerequisite for SLO-based operations.

---

## Opportunity 9: Prune Dependency Surface from 80+ to Essential Set

**Pain Point:** scope.md #10: "Large dependency surface (80+ deps)." Legacy assessment: Code & Dependency Health rated Poor. "80+ runtime dependencies including many unused OTEL instrumentors." "pymemcache, PyMySQL, pyzmq, python-consul, google-cloud-monitoring, boto (v2), unused OTEL instrumentors."

**Current State:** The `requirements.txt` contains 80+ pinned dependencies. Many are transitive from cnlib and have no direct use in the application:
- `pymemcache` — memcached client, not used.
- `PyMySQL` — MySQL client, not used.
- `pyzmq` — ZeroMQ, not used.
- `python-consul` — Consul client, not used.
- `google-cloud-monitoring`, `google-cloud-core` — Stackdriver/GCP libraries, not used (AWS-only service).
- `boto==2.49.0` — deprecated AWS SDK v2 (alongside boto3), no security patches since 2019.
- `pygerduty` — see Opportunity 7.
- OTEL instrumentors for unused libraries: `opentelemetry-instrumentation-sqlite3`, `opentelemetry-instrumentation-pymemcache`, `opentelemetry-instrumentation-pymysql`, `opentelemetry-instrumentation-threading`, `opentelemetry-instrumentation-asyncio`, `opentelemetry-instrumentation-click`, `opentelemetry-instrumentation-jinja2`, `opentelemetry-instrumentation-botocore`, `opentelemetry-instrumentation-boto`.
- `protobuf==3.20.3` — outdated, potential compatibility issues.
- `jsonschema==3.2.0` — replaced by Pydantic validation in FastAPI.

**Target State:** A minimal dependency set containing only what the application actually imports:
- `fastapi`, `uvicorn`, `uvloop` — web framework and ASGI server.
- `pydantic` — request/response validation (bundled with FastAPI).
- `confluent-kafka` — Kafka producer.
- `asyncpg` or `psycopg[binary]` — PostgreSQL with async support and connection pooling.
- `rebuilder-redis-module` — Redis client (standalone module).
- `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` — OTEL core only.
- `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-logging` — instrumentors for libraries actually in use.
- Standard library for HMAC (`hashlib`, `hmac`) — no external dependency.

Estimated dependency count: ~20–25 direct dependencies (down from 80+).

**Migration Path:**
1. Start with an empty `pyproject.toml`. Add dependencies only as they are needed during implementation.
2. Do not carry forward any dependency from legacy `requirements.txt` by default — each inclusion requires justification.
3. Run `pip-audit` in CI to gate on zero critical/high CVEs.
4. Pin exact versions in lock file. Use `>=` constraints only in `pyproject.toml`.
5. Audit transitive dependencies with `pip tree` — flag any unexpected transitive pulls.

**What Could Go Wrong:**
- **Missing transitive dependency.** A library that was silently provided by cnlib's dependency tree may be needed at runtime but not discovered until production. Mitigation: comprehensive test suite with high coverage, run in a clean virtual environment (not the legacy one).
- **`confluent-kafka` build complexity.** `confluent-kafka` requires `librdkafka` C library. The Docker build must either use a pre-built wheel or install `librdkafka-dev` in a builder stage. This adds build complexity compared to pure-Python alternatives.

**Impact:** High — reduces container image size, speeds up builds, eliminates unused CVE surface, and makes dependency auditing tractable.

---

## Opportunity 10: Add Terraform Infrastructure as Code

**Pain Point:** Legacy assessment, Operational Health: "No Terraform — infrastructure is Helm-only." "No auto-deploy to dev on merge. sha_ref in values.yaml is manually updated."

**Current State:** Infrastructure is managed entirely through Helm charts. There is no Terraform. Kubernetes resources (deployments, services, HPA, ingress) are defined in Helm values with per-environment overrides. AWS resources (RDS, Firehose streams, EKS cluster, IAM roles) were provisioned manually or via ad-hoc scripts — no reproducible provisioning. Deploying a new image version requires manually updating `sha_ref` in `values.yaml` and running `helm upgrade`. No auto-deploy pipeline.

**Target State:** Terraform manages all infrastructure:
- AWS resources: EKS node group configuration, IAM roles and policies, RDS instance configuration, Kafka topic provisioning (MSK or self-managed), Redis (ElastiCache), security groups, and networking.
- Environment-specific variable files: `envs/dev.tfvars`, `envs/staging.tfvars`, `envs/prod.tfvars`.
- State stored in S3 backend with DynamoDB locking.
- CI pipeline: `terraform plan` on PR, `terraform apply` on merge to main (dev auto-deploy).
- Helm retained for Kubernetes workload definition (deployment, service, HPA) but Terraform provisions the infrastructure those workloads run on.

**Migration Path:**
1. Inventory all infrastructure components from legacy Helm charts and AWS console.
2. Write Terraform modules for: EKS node group, IAM roles, security groups, ElastiCache Redis, Kafka topics, RDS configuration.
3. Configure S3 + DynamoDB state backend.
4. Add `terraform plan` step to CI pipeline (runs on every PR).
5. Add `terraform apply` step triggered on merge to main (deploys to dev).
6. Create environment-specific tfvars for dev, staging, prod.
7. Document manual promotion workflow for staging and prod.

**What Could Go Wrong:**
- **State import of existing resources.** Importing manually-created AWS resources (RDS, security groups) into Terraform state without disruption requires careful `terraform import` with exact attribute matching. Mismatched attributes cause Terraform to plan destructive changes.
- **Blast radius.** A misconfigured Terraform apply could destroy production infrastructure. Mitigation: separate state files per environment, require manual approval for staging/prod applies, use `prevent_destroy` lifecycle rules on critical resources.

**Impact:** High — enables reproducible infrastructure, auto-deploy to dev, environment parity, and auditable infrastructure changes.

---

## Opportunity Summary

| # | Opportunity | Pain Point(s) | Impact | Dependencies |
|---|---|---|---|---|
| 1 | Remove cnlib dependency | #1 — cnlib coupling | Critical | Blocks Opportunities 2, 9 |
| 2 | Replace Firehose with Kafka | #2 — Firehose → Kafka | Critical | Requires #1 (cnlib removal) |
| 3 | Extract standalone Redis module | #3 — no reusable Redis client | High | Independent; consumed by #4 |
| 4 | Replace file-based cache with Redis | #4 — fragile file cache | High | Requires #3 (Redis module) |
| 5 | Upgrade to Python 3.12+ | #5 — Python 3.10 behind LTS | Medium | Independent |
| 6 | Migrate Flask to FastAPI | #6 — no async; #7 — no OpenAPI | High | Benefits from #5 (Python 3.12) |
| 7 | Remove embedded PagerDuty | #8 — embedded PagerDuty | Medium | Independent |
| 8 | Add SRE diagnostic endpoints | #9 — no /ops/* endpoints | High | Benefits from #6 (FastAPI) |
| 9 | Prune dependency surface | #1, #10 — 80+ unused deps | High | Requires #1, #2, #7 |
| 10 | Add Terraform IaC | Operational gaps — no Terraform | High | Independent |
