# PRD: evergreen-tvevents Rebuild

> **Reference document.** This is the product requirements document from the ideation process. It informs implementation but does not override developer-agent/skill.md for coding standards or process rules.

## Background

evergreen-tvevents is a high-throughput TV telemetry ingestion microservice that receives event data from millions of Vizio SmartCast devices, validates security hashes, classifies events into three types, applies channel obfuscation, and delivers processed payloads to downstream analytics pipelines.

The legacy assessment identified key issues driving this rebuild:
- **Flask synchronous architecture** limits throughput and complicates async I/O patterns
- **AWS Kinesis Firehose vendor lock-in** via cnlib.firehose with up to 6 delivery streams
- **Zero test coverage** — no unit, integration, or contract tests
- **48 lines of manual OTEL boilerplate** instead of auto-instrumentation
- **No API documentation** — no OpenAPI spec, no Pydantic models, no formal request/response schemas
- **No CI/CD pipeline** visible in the repo
- **Fragile cnlib symlink** for vendored shared library
- **Flat requirements.txt** without hash pinning

The adjacent template-repo-python provides battle-tested patterns for FastAPI, OTEL auto-instrumentation, pip-compile, Helm charts, and containerization that this rebuild adopts.

## Goals

1. Replace Flask with FastAPI following template-repo-python patterns exactly — application factory, entry point, middleware, Dockerfile, entrypoint.sh, environment-check.sh, Helm charts
2. Replace AWS Kinesis Firehose with Apache Kafka via a standalone Kafka Python module outside the repo
3. Extract database access into a standalone RDS Python module outside the repo
4. Retain the file-based blacklist cache (NOT Redis) — preserve the 3-tier cache pattern (memory → file → RDS)
5. Implement OTEL auto-instrumentation via FastAPIInstrumentor (replace 48 lines of manual setup)
6. Achieve 80%+ test coverage with unit, integration, and contract tests
7. Auto-generate OpenAPI documentation via FastAPI + Pydantic models with json_schema_extra examples
8. Implement /ops/* SRE diagnostic endpoints for health, config, dependencies, cache status, and errors
9. Establish pip-compile workflow with hash pinning via scripts/lock.sh
10. Preserve T1_SALT security hash validation, all three event type classifications, and channel obfuscation logic with zero behavioral change

## Non-Goals

1. **Redis migration** — the file-cache works well for the small blacklist dataset. Do not replace it.
2. **Schema changes to the RDS blacklist table** — the table is read-only from this service and shared with other consumers. No DDL.
3. **API versioning** — the service has unknown inbound consumers. Root path preserved. Versioning evaluated in Phase 3 after consumer inventory.
4. **Full async rewrite** — Phase 1 uses sync internals with `asyncio.to_thread()` wrappers where needed. Native async drivers deferred to Phase 3.
5. **Downstream analytics changes** — consumer migration from Firehose to Kafka topics is outside this rebuild's scope.
6. **cnlib rewrite** — cnlib.token_hash and cnlib.log are used as-is. cnlib.firehose is dropped (replaced by Kafka module).
7. **Multi-region deployment** — current single-region EKS deployment pattern is maintained.

## Current Behavior

1. SmartCast device sends HTTP POST to `/` with JSON body containing tvid, client, h (security hash), EventType, timestamp, and event-specific payload
2. `before_request` middleware logs method, path, content-length
3. `validate_request()` checks:
   - Required params present (tvid, client, h, EventType, timestamp)
   - Timestamp within acceptable range
   - Params match expected patterns
   - Security hash matches T1_SALT HMAC via cnlib.token_hash.security_hash_match
4. `event_type_map[EventType]` dispatches to the correct EventType subclass:
   - NativeAppTelemetryEventType: validates Timestamp, extracts namespace from EventData
   - AcrTunerDataEventType: validates channelData/programData/Heartbeat, extracts namespace from TvEvent
   - PlatformTelemetryEventType: validates PanelData with PanelState ON/OFF, WakeupReason 0-128
5. Event type validates payload-specific requirements
6. `generate_output_json()` builds the output payload:
   - Flattens request JSON
   - Checks `should_obfuscate_channel()` (iscontentblocked flag + blacklist cache lookup)
   - If obfuscation needed: sets channelNum to 0, channelName to "Unknown"
   - Adds namespace from event type
7. `send_to_valid_firehoses()` delivers to up to 6 Firehose streams:
   - SEND_EVERGREEN controls evergreen streams (normal + debug)
   - SEND_LEGACY controls legacy streams (normal + debug)
   - ACR and platform types have additional variant streams
   - Parallel delivery via ThreadPoolExecutor
8. Returns 200 on success, 400 on validation error (with error details), 500 on unexpected failure
9. GET `/status` returns {"status": "ok", "version": VERSION}
10. Blacklist cache initializes at container startup from RDS, writes to JSON file, serves from memory

## Target Behavior

1. SmartCast device sends HTTP POST to `/` with JSON body (identical request format — backward compatible)
2. FastAPI middleware logs method, path, content-length (skips /status and /health)
3. Request validation pipeline (ported logic, identical behavior):
   - Required params checked via Pydantic model validation
   - Timestamp range check preserved
   - Params pattern match preserved
   - T1_SALT security hash validation via cnlib.token_hash (unchanged)
4. Event type classification (ported logic, identical dispatch):
   - Same three EventType subclasses with identical validation rules
   - Same event_type_map dispatch
5. Output JSON generation (ported logic, identical output format):
   - Same flattening, obfuscation, namespace extraction
   - Blacklist cache: memory → file → RDS (via standalone RDS module)
   - File cache path from BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH (unchanged)
6. Kafka delivery (replacing Firehose):
   - Firehose stream names mapped to Kafka topic names
   - Same parallel delivery pattern
   - Same SEND_EVERGREEN / SEND_LEGACY controls
   - JSON payloads byte-for-byte identical to Firehose payloads
7. Response format unchanged — 200/400/500 with same JSON shapes
8. GET `/status` returns {"status": "ok", "version": VERSION}
9. NEW: GET `/ops/health` — deep health check (Kafka, RDS, cache)
10. NEW: GET `/ops/config` — non-sensitive runtime config
11. NEW: GET `/ops/dependencies` — dependency status
12. NEW: GET `/ops/cache` — cache statistics and freshness
13. NEW: GET `/ops/errors` — recent error summary
14. Blacklist cache initializes at startup with graceful degradation — warns instead of failing if RDS unreachable but cache file exists

## Target Repository

`rebuilder-evergreen-tvevents` — all new code goes here. The legacy `evergreen-tvevents` repo is never modified.

## Technical Approach

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                    │
│                                                          │
│  app/__init__.py   ─── create_app() factory             │
│  app/main.py       ─── uvicorn entry point              │
│  app/routes.py     ─── POST /, GET /status, /ops/*      │
│  app/validation.py ─── request validation + T1_SALT     │
│  app/event_type.py ─── 3 event type classifiers         │
│  app/output.py     ─── output JSON generation           │
│  app/obfuscation.py ── channel obfuscation logic        │
│  app/blacklist.py  ─── 3-tier cache (mem→file→RDS)      │
│  app/exceptions.py ─── custom exception hierarchy       │
│                                                          │
│  ┌───────────────┐      ┌────────────────┐              │
│  │ Standalone     │      │ Standalone      │             │
│  │ RDS Module     │      │ Kafka Module    │             │
│  │ (external pkg) │      │ (external pkg)  │             │
│  └───────┬───────┘      └───────┬────────┘              │
│          │                       │                       │
└──────────┼───────────────────────┼───────────────────────┘
           │                       │
     ┌─────▼─────┐         ┌──────▼──────┐
     │ PostgreSQL │         │   Apache    │
     │    RDS     │         │   Kafka     │
     └───────────┘         └─────────────┘
```

### Stack Decisions

- **FastAPI** over Flask: native async, Pydantic validation, OpenAPI auto-gen, dependency injection. Non-negotiable constraint.
- **uvicorn** over Gunicorn+gevent: ASGI-native, no monkey-patching, simpler process model. Template-proven.
- **Kafka** over Firehose: decouples from AWS-specific delivery service. Non-negotiable constraint.
- **Standalone modules** for RDS and Kafka: clean dependency boundaries, independent versioning, reusable across services. Non-negotiable constraint.
- **File-cache not Redis**: the blacklist dataset is small (fits in memory). Adding Redis infrastructure complexity is unjustified. Non-negotiable constraint.
- **OTEL auto-instrumentation**: eliminates 48 lines of manual provider setup. Template pattern. Non-negotiable constraint.
- **psycopg2 initially**: the sync driver works via `to_thread()`. Async driver (psycopg3) in Phase 3 after the module interface is stable.
- **cnlib retained**: token_hash for security hash, log for structured logging. firehose module dropped.

### Directory Structure

```
src/
  app/
    __init__.py         # FastAPI factory (create_app)
    main.py             # uvicorn entry point
    routes.py           # API routes + /ops/* SRE endpoints
    validation.py       # Request validation + T1_SALT
    event_type.py       # EventType base + 3 implementations
    output.py           # Output JSON generation + flattening
    obfuscation.py      # Channel obfuscation logic
    blacklist.py        # 3-tier cache (memory → file → RDS)
    exceptions.py       # Custom exception hierarchy
tests/
  conftest.py           # Fixtures: FastAPI test client, mock Kafka/RDS modules
  test_validation.py
  test_event_types.py
  test_output.py
  test_obfuscation.py
  test_blacklist.py
  test_routes.py
  test_ops_endpoints.py
scripts/
  lock.sh               # pip-compile workflow
charts/
  Chart.yaml
  values.yaml
  templates/            # Helm templates from template-repo-python
Dockerfile
entrypoint.sh
environment-check.sh
pyproject.toml
```

## API Design

### POST `/`

**Request:** JSON body with TV event data.

```json
{
  "tvid": "string (required)",
  "client": "string (required)",
  "h": "string (required — T1_SALT HMAC hash)",
  "EventType": "string (required — NativeAppTelemetry|AcrTunerData|PlatformTelemetry)",
  "timestamp": "string (required — ISO 8601)",
  "EventData": {},
  "TvEvent": {},
  "PanelData": {}
}
```

**Response 200:** `{"status": "ok"}`
**Response 400:** `{"error": "<error type>", "message": "<detail>"}`
**Response 500:** `{"error": "internal_error", "message": "<detail>"}`

All request and response bodies have Pydantic models with `json_schema_extra` examples. Swagger UI fully functional at `/docs`.

### GET `/status`

**Response 200:** `{"status": "ok", "version": "<VERSION>"}`

### GET `/ops/health`

**Response 200:**
```json
{
  "status": "healthy",
  "checks": {
    "kafka": {"status": "ok", "latency_ms": 5},
    "rds": {"status": "ok", "latency_ms": 12},
    "cache": {"status": "ok", "entries": 1500, "age_seconds": 3600}
  }
}
```

### GET `/ops/config`

**Response 200:** Non-sensitive runtime configuration (event types enabled, Kafka topics, cache file path, OTEL status). No secrets.

### GET `/ops/dependencies`

**Response 200:** Status of each external dependency with connectivity check.

### GET `/ops/cache`

**Response 200:** Blacklist cache statistics — entry count, file age, last refresh time, memory/file/db tier hit rates.

### GET `/ops/errors`

**Response 200:** Recent error summary — count by type over last N minutes.

## Observability & SRE

### OTEL Auto-Instrumentation

`FastAPIInstrumentor.instrument_app(app)` plus:
- Psycopg2Instrumentor (via standalone RDS module)
- URLLib3Instrumentor
- Additional instrumentors as the dependency tree requires

All configured via `opentelemetry-bootstrap` in Dockerfile (template pattern).

### Golden Signals

| Signal | Metric | Source |
|---|---|---|
| Latency | `http.server.duration` histogram (p50/p95/p99) | FastAPI auto-instrumentation |
| Traffic | `http.server.request.count` counter by endpoint | FastAPI auto-instrumentation |
| Errors | `http.server.error.count` counter by status code | Custom middleware |
| Saturation | Connection pool utilization, event loop lag | Custom metrics |

### Custom Application Metrics (ported from legacy + new)

| Metric | Type | Labels | Source |
|---|---|---|---|
| `db.connection.count` | Counter | status (success/failure) | RDS module |
| `db.query.duration` | Histogram | query_name | RDS module |
| `cache.read.count` | Counter | tier (memory/file/db), result (hit/miss) | blacklist.py |
| `cache.write.count` | Counter | target (memory/file) | blacklist.py |
| `kafka.send.count` | Counter | topic, status (success/failure) | Kafka module |
| `kafka.send.duration` | Histogram | topic | Kafka module |
| `event.type.count` | Counter | event_type | routes.py |
| `validation.failure.count` | Counter | reason | validation.py |

### SLOs

| SLO | Target | Error Budget |
|---|---|---|
| POST `/` success rate | 99.9% | 0.1% (43.2 min/month) |
| POST `/` p99 latency | < 200ms | Measured over 30-day window |
| Kafka delivery success rate | 99.95% | 0.05% |

### /ops/* SRE Agent Endpoints

Diagnostic (read-only):
- `/ops/health` — deep health with Kafka, RDS, cache checks
- `/ops/config` — runtime configuration (no secrets)
- `/ops/dependencies` — dependency status with latency
- `/ops/cache` — cache statistics and freshness
- `/ops/errors` — recent error summary by type

Safe remediation:
- POST `/ops/cache/refresh` — trigger blacklist cache refresh from RDS
- POST `/ops/log-level` — change log level at runtime (body: `{"level": "DEBUG"}`)

**Embedded Monitoring Removal:** The legacy codebase has no embedded vendor-specific monitoring clients (no PagerDuty SDK, no Datadog agent, no custom StatsD emitters). OTEL is already the telemetry standard. New Relic integration is via OTEL export headers, not via an embedded agent — this pattern continues. No alerting clients to remove.

## Auth & RBAC

- **Machine-to-Machine Auth:** T1_SALT HMAC security hash validation on every POST `/` request. Implementation via cnlib.token_hash.security_hash_match (unchanged from legacy). Salt stored as environment variable from Kubernetes Secret.
- **RBAC:** Not applicable. This is a device-to-service data ingestion endpoint with no human user sessions or roles.
- **Service-to-Service:** Kafka and RDS access authenticated via infrastructure credentials (Kubernetes Secrets → environment variables). No application-level service mesh auth.
- **Audit Logging:** Security hash validation failures logged with request metadata in OTEL traces. All /ops/* remediation actions logged.

## External Dependencies & Contracts

### 1. PostgreSQL RDS — Blacklist Data

- **Name and type:** PostgreSQL RDS — managed service
- **Direction:** Outbound (this service reads from it)
- **Interface:** Direct DB via psycopg2 through standalone RDS module
- **Contract status:** Documented. Single query: `SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map`. Read-only. No writes.
- **Inside/outside rebuild boundary:** Outside. The RDS instance is shared infrastructure. The standalone RDS module is inside the rebuild boundary.
- **Fallback behavior:** File cache serves stale data. Application logs a warning but continues operating. Memory cache is populated from file if available.
- **SLA expectation:** 99.95% availability (RDS Multi-AZ). Query latency < 50ms.
- **Integration tests:** RDS module tested with PostgreSQL container. App tested with mock RDS module.

### 2. Apache Kafka — Event Delivery

- **Name and type:** Apache Kafka (AWS MSK or standalone) — managed service
- **Direction:** Outbound (this service produces messages)
- **Interface:** Kafka producer via standalone Kafka module
- **Contract status:** Must be documented as part of rebuild. Topic names map from legacy Firehose stream names. Message format: JSON, identical to legacy Firehose payload. Partitioning: by tvid for ordering guarantee per device.
- **Inside/outside rebuild boundary:** Outside. Kafka cluster is shared infrastructure. The standalone Kafka module is inside the rebuild boundary.
- **Fallback behavior:** Failed deliveries logged and counted. HTTP 500 returned to caller. No silent message loss.
- **SLA expectation:** 99.95% availability. Produce latency < 50ms p99.
- **Integration tests:** Kafka module tested with Kafka container (testcontainers). App tested with mock Kafka module.

### 3. cnlib — Shared Internal Library

- **Name and type:** cnlib (from cntools_py3) — internal library
- **Direction:** Bidirectional (imported into this service)
- **Interface:** Python imports: `cnlib.token_hash.security_hash_match`, `cnlib.log`
- **Contract status:** Documented by usage. security_hash_match(salt, params) → bool. log provides a configured structured logger.
- **Inside/outside rebuild boundary:** Inside (vendored in container image)
- **Fallback behavior:** No fallback. Security hash validation is mandatory for every request.
- **SLA expectation:** N/A — in-process library
- **Integration tests:** Unit tests with known hash inputs/outputs

### 4. Inbound Consumers — SmartCast TV Devices

- **Name and type:** Vizio SmartCast TV fleet — device firmware
- **Direction:** Inbound (devices call this service)
- **Interface:** HTTP POST `/` with JSON body
- **Contract status:** Undocumented — must be documented as part of rebuild. Required params: tvid, client, h, EventType, timestamp. Three event type payload schemas. T1_SALT HMAC in `h` parameter.
- **Inside/outside rebuild boundary:** Outside (firmware is immutable from this service's perspective)
- **Fallback behavior:** N/A (these are the callers)
- **SLA expectation:** Service must maintain 99.9% success rate and < 200ms p99 to avoid device-side timeout retries.
- **Integration tests:** Contract tests verifying backward-compatible response shapes for 200, 400, 500

### 5. Downstream Analytics Pipeline

- **Name and type:** Analytics consumers reading from Kafka topics — internal services
- **Direction:** Indirect outbound (this service writes to Kafka; downstream reads from Kafka)
- **Interface:** Kafka topics (message format: JSON)
- **Contract status:** Undocumented — JSON payload format must be byte-for-byte identical to legacy Firehose output
- **Inside/outside rebuild boundary:** Outside
- **Fallback behavior:** Outside application scope. Downstream consumers handle their own retry/backfill.
- **SLA expectation:** N/A from this service's perspective
- **Integration tests:** Parity tests comparing Kafka payloads against captured Firehose output fixtures

## Data Migration Plan

### Database Schema
No migration required. The `public.tvevents_blacklisted_station_channel_map` table is read-only from this service. Schema is unchanged. Same RDS instance, same table, same query.

### Cache File
No migration required. Same JSON format (`json.dump` / `json.load` of channel ID list). Same file path from `BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH` environment variable.

### Delivery Stream → Topic Mapping

| Legacy Firehose Stream | Kafka Topic | Condition |
|---|---|---|
| EVERGREEN_FIREHOSE_NAME | evergreen-tvevents | SEND_EVERGREEN=True |
| EVERGREEN_DEBUG_FIREHOSE_NAME | evergreen-tvevents-debug | SEND_EVERGREEN=True |
| LEGACY_FIREHOSE_NAME | legacy-tvevents | SEND_LEGACY=True |
| LEGACY_DEBUG_FIREHOSE_NAME | legacy-tvevents-debug | SEND_LEGACY=True |
| ACR variant streams | acr-tvevents, acr-tvevents-debug | EventType=AcrTunerData |
| Platform variant streams | platform-tvevents, platform-tvevents-debug | EventType=PlatformTelemetry |

Topic names are configurable via environment variables, replacing the Firehose stream name env vars.

### Environment Variable Migration

| Legacy Variable | Replacement Variable | Notes |
|---|---|---|
| EVERGREEN_FIREHOSE_NAME | KAFKA_TOPIC_EVERGREEN | Topic name |
| LEGACY_FIREHOSE_NAME | KAFKA_TOPIC_LEGACY | Topic name |
| EVERGREEN_DEBUG_FIREHOSE_NAME | KAFKA_TOPIC_EVERGREEN_DEBUG | Topic name |
| LEGACY_DEBUG_FIREHOSE_NAME | KAFKA_TOPIC_LEGACY_DEBUG | Topic name |
| SEND_EVERGREEN | SEND_EVERGREEN | Unchanged |
| SEND_LEGACY | SEND_LEGACY | Unchanged |
| FLASK_ENV | (dropped) | Not needed with FastAPI |
| FLASK_APP | (dropped) | Not needed with FastAPI |
| — | KAFKA_BROKERS | New: comma-separated broker list |
| — | KAFKA_SECURITY_PROTOCOL | New: SASL_SSL or PLAINTEXT |
| — | KAFKA_SASL_MECHANISM | New: SCRAM-SHA-512 or similar |
| — | KAFKA_USERNAME | New: for SASL auth |
| — | KAFKA_PASSWORD | New: for SASL auth |

## Rollout Plan

### Phase 0: Shadow Deployment
1. Deploy rebuilt service alongside legacy on same EKS cluster
2. Route shadow traffic (copy of production requests) to new service
3. Compare Kafka output payloads against Firehose output for parity
4. Monitor error rate, latency, and resource utilization for 48 hours minimum

### Phase 1: Canary
1. Route 5% of production traffic to new service
2. Legacy handles remaining 95% + continues Firehose delivery
3. Monitor Golden Signals for 24 hours
4. Expand to 25%, then 50%, then 100%

### Phase 2: Cutover
1. Switch 100% of traffic to new service
2. Legacy service remains deployed but receives no traffic (hot standby)
3. Downstream consumers switch from Firehose streams to Kafka topics

### Phase 3: Decommission
1. After 2 weeks of stable operation, decommission legacy service
2. Remove Firehose stream infrastructure
3. Archive legacy repository

### Rollback Triggers
- Error rate > 1% (sustained 5 minutes)
- p99 latency > 500ms (sustained 5 minutes)
- Kafka delivery failure rate > 0.1%
- Any data loss detected in parity comparison

### Rollback Action
Switch ingress back to legacy service. No data to undo — blacklist table is read-only and shared. Kafka topic consumers paused until investigated.

## Success Criteria

1. **Functional Parity:** All three event types validated and processed identically. Output JSON payloads byte-for-byte match legacy Firehose output.
2. **Test Coverage:** ≥ 80% code coverage. All business logic paths tested. All error paths tested.
3. **Performance:** p99 latency < 200ms under production load. No regression from legacy baseline.
4. **Reliability:** 99.9% success rate over 30-day window post-cutover.
5. **Observability:** All Golden Signals visible in monitoring. /ops/* endpoints respond correctly. OTEL traces flow to New Relic.
6. **Security:** T1_SALT validation works identically. No new security vulnerabilities. Dependencies hash-pinned.
7. **Developer Experience:** OpenAPI docs at /docs functional. Tests pass locally. CI/CD pipeline green. Local dev via docker-compose works.
8. **Standards Compliance:** Matches template-repo-python patterns for: factory, entry point, Dockerfile, entrypoint.sh, environment-check.sh, Helm charts, pip-compile.

## ADRs Required

1. **Framework Selection** — FastAPI over Flask. Document async benefits, OpenAPI auto-gen, Pydantic validation, template alignment.
2. **Delivery Infrastructure** — Kafka over Firehose. Document decoupling, standalone module pattern, topic mapping strategy.
3. **Database Access Pattern** — Standalone RDS module. Document module boundary, connection pooling, interface design.
4. **Cache Strategy** — File-cache retention over Redis. Document rationale (small dataset, no infrastructure overhead, battle-tested pattern).
5. **Observability Approach** — OTEL auto-instrumentation over manual setup. Document boilerplate reduction, template alignment, instrumentor list.
6. **Dependency Management** — pip-compile over flat requirements. Document hash pinning, reproducibility, lock.sh workflow.
7. **API Versioning (Deferred)** — Document decision to preserve root path `/` for backward compatibility with unknown consumers. Version prefix deferred to Phase 3.

## Open Questions

1. **Kafka topic names** — Are the names in the Delivery Stream → Topic Mapping table correct, or does the Kafka infrastructure team have a naming convention?
2. **Kafka cluster** — Is this AWS MSK or a self-managed Kafka cluster? What version? What auth mechanism?
3. **Consumer migration timeline** — When can downstream analytics consumers switch from Firehose to Kafka topics? This determines the parallel-run duration.
4. **ACR MSK credentials** — The legacy environment-check.sh references `acr_data_msk_vars` (USERNAME/PASSWORD). Are these the same Kafka credentials, or separate?
5. **T1_SALT rotation** — Is there a planned rotation mechanism for the T1_SALT secret? The rebuild preserves the current pattern but doesn't add rotation.
6. **KEDA scaling parameters** — Should the KEDA autoscaling configuration (1–500) be retuned for uvicorn's different process model?
7. **Standalone module hosting** — Where are the standalone RDS and Kafka Python packages published? Private PyPI? Git submodules? Direct pip+git install?
