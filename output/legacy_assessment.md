# Legacy Assessment

## Application Overview

**evergreen-tvevents** (also `tvevents-k8s`) is a Python 3.10 Flask service that collects TV event telemetry from Vizio SmartCast TVs. It receives JSON payloads via a single POST endpoint, validates them against HMAC security hashes and event-type-specific schemas, checks for blacklisted channels via PostgreSQL (AWS RDS), obfuscates restricted content, and delivers processed events to AWS Kinesis Data Firehose streams for downstream analytics. The service runs on AWS EKS and scales from 1 pod (dev) to 300–500 pods (production), processing high-volume continuous telemetry from millions of TV devices.

The application depends on `cntools_py3/cnlib` — an internal shared library bundled as a git submodule — for Firehose delivery, HMAC hash validation, and logging. This dependency is the primary pain point driving the rebuild.

## Architecture Health
- Rating: **Acceptable**
- The application has a clear, simple architecture: receive → validate → transform → deliver. Each concern is separated into distinct modules (`routes.py`, `utils.py`, `event_type.py`, `dbhelper.py`).
- The event type system uses a clean polymorphic pattern with an abstract base class and a dispatch map.
- However, `utils.py` is a grab-bag module that mixes validation logic, output generation, firehose delivery, and data transformation — 417 lines doing too many things.
- The cnlib dependency creates tight coupling to an external shared library for core functionality (hash validation, data delivery).
- No dependency injection — all dependencies are module-level globals (`TVEVENTS_RDS`, `VALID_TVEVENTS_FIREHOSES`, `SALT_KEY`).
- No async support — uses gevent monkey-patching for concurrency, which adds implicit complexity.

## API Surface Health
- Rating: **Poor**
- Only 2 endpoints: POST `/` and GET `/status`.
- No OpenAPI specification. No automatic documentation.
- No API versioning — endpoints are bare paths.
- No typed response models — returns plain strings ("OK") or `jsonify()` dicts.
- Error handling wraps all exceptions into `TvEventsCatchallException` with a 400 status code, losing error specificity.
- The POST endpoint uses query parameters (`tvid`, `event_type`) alongside a JSON body, mixing parameter passing styles.
- No pagination, rate limiting, or request size validation at the application level.

## Observability & SRE Readiness
- Rating: **Acceptable**
- OpenTelemetry is comprehensively instrumented: traces span every function, custom metrics counters track DB operations, cache operations, firehose sends, and payload validation.
- OTLP HTTP export to New Relic is configured and functional.
- Structured logging with OTEL correlation (trace/span IDs in log messages).
- **Gaps**: No SLOs/SLAs defined. No `/ops/*` diagnostic endpoints. `/status` returns "OK" regardless of whether RDS or Firehose are reachable. No graceful drain mechanism. PagerDuty is embedded via `pygerduty` rather than handled externally. No saturation metrics (memory, connection pool, queue depth).

## Auth & Access Control
- Rating: **Acceptable**
- HMAC security hash validation is functional — TVs compute `h` from `tvid` + salt, app verifies via `cnlib.token_hash.security_hash_match()`.
- **Concerns**: It's unclear whether `security_hash_match` uses constant-time comparison (delegated to cnlib, which is an empty submodule in the clone). The `T1_SALT` is loaded from a plain environment variable, not a secrets manager. There is no RBAC — any client with the salt can post events. No service-to-service auth scoping for Firehose/RDS access beyond broad AWS credentials.

## Code & Dependency Health
- Rating: **Poor**
- **Python 3.10**: One major version behind current LTS (3.12).
- **cntools_py3 submodule**: Bundles Redis, memcached, ZeroMQ, MySQL, Consul, and many other libraries the app doesn't use. The submodule is not initialized in the git clone — CI requires explicit `submodules: true` checkout. Functions actually used from cnlib: `firehose.Firehose`, `token_hash.security_hash_match`, `log.getLogger` — 3 functions from a massive shared library.
- **Dependency bloat**: 80+ runtime dependencies. Many are unused by the application directly: `pymemcache`, `PyMySQL`, `pyzmq`, `python-consul`, `google-cloud-monitoring`, `google-cloud-core`, `boto` (v2, alongside boto3). Multiple OTEL instrumentors installed for libraries not used by the app (sqlite3, pymemcache, pymysql, threading, asyncio, click, jinja2, botocore, boto).
- **pygerduty**: Embedded PagerDuty SDK — alerting should be external.
- **protobuf 3.20.3**: Outdated, potential compatibility issues.
- **No type annotations**: `mypy` configured with `ignore_missing_imports = true` — not providing meaningful type safety.
- **Mutable default argument**: `flatten_request_json(request_json, key_prefix='', ignore_keys=[])` — classic Python bug pattern.
- **pylint disables**: 10+ pylint disables scattered across the codebase (`W0246`, `R1710`, `W1508`, `R1720`, `C0415`, `C0301`, `W0707`, `W0102`, `W0107`).
- **No dependency pinning in lock file**: `requirements.txt` uses hashes but versions are pinned there, not in `pyproject.toml` constraints.

## Operational Health
- Rating: **Acceptable**
- Containerized with Docker, deployed to EKS via Helm charts.
- GitHub Actions CI pipeline includes: Black formatting, pytest, pylint, mypy, complexipy, Docker build+push, CVE scanning via Docker Scout, VEX documentation for accepted CVEs.
- Helm values configure per-environment scaling (dev: 1–10 pods, prod: 300–500 pods) with CPU-based HPA.
- Rolling deployment strategy (50% maxSurge, 25% maxUnavailable).
- Health probes configured (liveness: 90s interval, readiness: 17s interval).
- **Gaps**: No Terraform — infrastructure is Helm-only. No auto-deploy to dev on merge (manual image tag updates in values.yaml). No integration test stage in CI. `sha_ref` in values.yaml is manually updated. No graceful shutdown/drain mechanism visible.

## Data Health
- Rating: **Acceptable**
- Small data model: single read-only table `public.tvevents_blacklisted_station_channel_map` with `channel_id` column.
- No schema migrations — table is externally managed.
- Application opens a new PostgreSQL connection per query (`_execute` creates and closes connections) — no connection pooling.
- File-based cache for blacklisted channel IDs — fragile, not shared across pods, lost on pod restarts.
- In-memory cache (`_blacklisted_channel_ids`) is per-process, never explicitly refreshed (only populated once).
- Output data format is a flattened JSON structure — this format is a contract with downstream consumers.

## Developer Experience
- Rating: **Acceptable**
- README documents setup requirements (Helm, Minikube, Docker), expected environment variables, and CVE tooling.
- Local development requires: Docker, Minikube, Helm, AWS credentials, RDS access, valid T1_SALT — significant setup burden.
- Tests exist (17 test files, ~1,800 test lines) covering most utility functions and event types.
- CI runs tests, lint, format checks, type checks, and complexity analysis.
- **Gaps**: No `.env.example` file. The `env.list` file contains real development hostnames. No seed data script. No `docker compose` for local development — requires full Minikube cluster. No contribution guide.

## Infrastructure Health
- Rating: **Acceptable**
- Cloud Provider(s): AWS
- Containerized: Yes — Docker with pinned base image (`python:3.10-bookworm` with SHA digest)
- IaC: Helm charts only — no Terraform
- Managed Services: AWS RDS PostgreSQL, AWS Kinesis Data Firehose, AWS EKS
- Provider Lock-in: **Medium** — Firehose delivery is AWS-specific (via cnlib/boto3). RDS PostgreSQL is portable. EKS/Helm is portable to any Kubernetes provider. The cloud-specific coupling is in the data delivery layer.
- Docker image: Runs as non-root user (`flaskuser:10000`), has healthcheck, removes unnecessary packages. Good container hygiene.
- **Gaps**: Base image is `python:3.10-bookworm` (full Debian) — should be `slim` variant. Many apt packages installed for CVE remediation that may not be needed. Dockerfile copies cnlib and runs `setup.py install` — legacy packaging pattern.

## External Dependencies & Integration Health
- Rating: **Acceptable**
- Outbound Dependencies: AWS Kinesis Data Firehose (via cnlib), AWS RDS PostgreSQL (via psycopg2)
- Inbound Consumers: Vizio SmartCast TVs (via Kong), Kubernetes probes
- Shared Infrastructure: RDS PostgreSQL `tvevents` database (shared with unknown services)
- Internal Libraries: cntools_py3/cnlib (git submodule — `firehose`, `token_hash`, `log`)
- Data Dependencies: Downstream S3 data lake and analytics pipelines consume Firehose output
- Tightly Coupled: cnlib — cannot be stubbed without reimplementation. This is the primary target for the rebuild.
- **Risk**: Unknown inbound consumers beyond TVs. Unknown services sharing the RDS database. Unknown downstream consumers of the S3/data lake output format — the flattened JSON structure is an implicit contract.

## Summary
- Overall Risk Level: **Medium**
- Top 3 Risks:
  1. **cnlib dependency**: Tightly coupled shared library bundles unused dependencies, complicates CI, and is the sole provider of critical functionality (hash validation, firehose delivery)
  2. **Unknown consumers**: Both inbound API consumers and downstream data format consumers are partially unknown — output JSON format changes could break pipelines
  3. **No connection pooling / file-based cache**: Per-request DB connections and file-based caching are fragile at 300–500 pod production scale
- Strongest Assets to Preserve:
  1. **Event type polymorphism**: Clean abstract class + dispatch map pattern for event type handling
  2. **OTEL instrumentation**: Comprehensive tracing and metrics already in place
  3. **Validation logic**: Well-tested payload validation across event types
  4. **Container security**: Non-root user, pinned base image, CVE tracking
