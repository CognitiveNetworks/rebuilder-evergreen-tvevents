# PRD: rebuilder-evergreen-tvevents

## Background

The evergreen-tvevents application (`tvevents-k8s`) collects TV event telemetry from millions of Vizio SmartCast TVs. The legacy assessment (Step 1) rated Code & Dependency Health and API Surface Health as **Poor**, driven by:

- Tight coupling to `cntools_py3/cnlib` — a git submodule providing HMAC validation, Firehose delivery, and logging while bundling 80+ transitive dependencies the app doesn't use
- AWS Kinesis Firehose as the sole delivery mechanism — the organization is standardizing on Apache Kafka
- No standalone Redis abstraction — other services need a reusable Redis client
- No OpenAPI spec, no typed responses, no SRE diagnostic endpoints
- File-based blacklist cache fragile at 300–500 pod production scale
- Python 3.10 / Flask with gevent monkey-patching instead of native async

All 10 modernization opportunities passed feasibility analysis with a Go verdict. This PRD covers the single rebuild candidate: full-stack modernization.

## Goals

1. Remove `cntools_py3/cnlib` dependency entirely — zero functions consumed from the shared library
2. Deliver a standalone Redis Python module (`rebuilder-redis-module`) usable by any service
3. Replace Kinesis Firehose with Apache Kafka for event delivery
4. Preserve exact payload validation logic (HMAC hash, event type schemas) and output JSON format
5. Achieve ≥80% unit test coverage with domain-realistic TV telemetry test data
6. Expose full `/ops/*` SRE diagnostic and remediation endpoints with Golden Signals
7. Generate OpenAPI specification with Pydantic response models and Swagger UI examples
8. Replace file-based blacklist cache with Redis-backed TTL cache
9. Reduce runtime dependencies from 80+ to ~20–25

## Non-Goals

1. Database schema changes to `tvevents_blacklisted_station_channel_map` — the table is shared and externally managed
2. Downstream data lake or analytics pipeline changes — output JSON format is preserved
3. Cloud provider migration — staying on AWS
4. Kong API Gateway configuration changes (handled by infrastructure team)
5. Frontend development (none exists)
6. DAI/ZeroMQ integration — the legacy `pyzmq` dependency was a cnlib transitive and not used by this app
7. Multi-region deployment — current single-region architecture is sufficient

## Current Behavior

1. TV sends POST request to Kong Gateway with query params (`tvid`, `event_type`) and JSON body containing `TvEvent` envelope with security hash `h`, `EventType`, `timestamp`, `client`, and `EventData`
2. Flask service validates: required params present, `tvid` matches between URL and body, HMAC hash matches via `cnlib.token_hash.security_hash_match(tvid, h, salt)`
3. Event-type-specific validation runs via polymorphic `EventType` classes (ACR_TUNER_DATA, PLATFORM_TELEMETRY, NATIVEAPP_TELEMETRY)
4. Output JSON generated: `TvEvent` fields flattened (except `h`, `timestamp`, `EventType`), `EventData` flattened per event type rules, `zoo` environment added
5. Blacklist check: if `channelid` is in blacklisted set (from RDS cache) or `iscontentblocked` is true → obfuscate `channelid`, `programid`, `channelname` with "OBFUSCATED"
6. Send to configured Firehose streams (evergreen + legacy + debug variants) via `cnlib.firehose.Firehose` in parallel threads
7. Health: GET `/status` returns plain text "OK" regardless of dependency state

## Target Behavior

1. TV sends POST request to Kong Gateway routed to `/v1/events` with same query params and JSON body
2. FastAPI validates request with Pydantic models. Standalone HMAC validation using `hmac.compare_digest()` with salt from AWS Secrets Manager
3. Same event-type-specific validation logic via refactored domain classes with Pydantic integration
4. Same output JSON generation logic — format preserved exactly for downstream compatibility
5. Blacklist check: Redis-backed cache (via `rebuilder-redis-module`) with TTL refresh from RDS; graceful degradation to RDS query on cache miss
6. Kafka producer sends to configured topics with `acks=all`, idempotence enabled, dead-letter topic for failures
7. Health: GET `/health` checks Kafka, RDS, Redis connectivity — returns 503 if any critical dependency is down
8. Full `/ops/*` diagnostic suite: status, health, metrics, config, dependencies, errors, drain, cache/flush, circuits, loglevel, scale

## Target Repository

`rebuilder-evergreen-tvevents` — all new code goes here. The legacy `evergreen-tvevents` repo is never modified.

Additionally, `rebuilder-redis-module` — standalone Redis Python package, separate repo.

## Technical Approach

### Architecture

```
rebuilder-evergreen-tvevents/
├── src/
│   └── tvevents/
│       ├── __init__.py          # Package init
│       ├── main.py              # FastAPI app factory, lifespan, OTEL setup
│       ├── config.py            # Pydantic Settings for all configuration
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes.py        # POST /v1/events endpoint
│       │   ├── health.py        # GET /health endpoint
│       │   └── models.py        # Pydantic request/response models
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── event_types.py   # Event type validation + transformation
│       │   ├── validation.py    # HMAC validation, required params
│       │   └── obfuscation.py   # Channel blacklist + obfuscation logic
│       ├── services/
│       │   ├── __init__.py
│       │   ├── kafka_producer.py  # Kafka event delivery
│       │   ├── rds_client.py      # Async PostgreSQL client
│       │   └── cache.py           # Redis cache via rebuilder-redis-module
│       ├── ops/
│       │   ├── __init__.py
│       │   ├── diagnostics.py   # /ops/status, health, metrics, config, deps, errors
│       │   └── remediation.py   # /ops/drain, cache/flush, circuits, loglevel, scale
│       └── middleware/
│           ├── __init__.py
│           └── metrics.py       # Request metrics middleware (Golden Signals)
├── tests/
│   ├── conftest.py
│   ├── test_routes.py
│   ├── test_event_types.py
│   ├── test_validation.py
│   ├── test_obfuscation.py
│   ├── test_kafka_producer.py
│   ├── test_rds_client.py
│   ├── test_cache.py
│   ├── test_ops.py
│   └── test_models.py
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── envs/
│       ├── dev.tfvars
│       ├── staging.tfvars
│       └── prod.tfvars
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .github/
│   ├── copilot-instructions.md
│   └── workflows/
│       └── ci.yml
├── .windsurfrules
├── developer-agent/
│   ├── skill.md
│   └── config.md
└── README.md
```

### Tech Stack

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Language | Python | 3.12 | Current LTS, performance improvements, better error messages |
| Framework | FastAPI | ≥0.115 | Native async, auto-OpenAPI, Pydantic integration, dependency injection |
| ASGI Server | Uvicorn | ≥0.32 | Production ASGI server, HTTP/1.1 + HTTP/2 |
| Validation | Pydantic v2 | ≥2.10 | Fast, typed validation with JSON Schema generation |
| Database | asyncpg | ≥0.30 | Async PostgreSQL driver with connection pooling |
| Cache | rebuilder-redis-module | 1.0.0 | Standalone Redis client with async, pooling, OTEL |
| Message Queue | confluent-kafka | ≥2.6 | Production Kafka client with librdkafka |
| OTEL | opentelemetry-sdk | ≥1.28 | Standard observability |
| Testing | pytest + pytest-asyncio + httpx | Latest | Async test support with ASGI test client |
| Linting | ruff | Latest | Fast linter + formatter |
| Type Checking | mypy | Latest (strict mode) | Full type safety |

## API Design

### POST `/v1/events`

Request: Same JSON body as legacy (backward compatible). Query params: `tvid`, `event_type`.

```json
{
  "TvEvent": {
    "tvid": "ITV00C000000000000001",
    "client": "smtv",
    "h": "a1b2c3d4e5f67890abcdef1234567890",
    "EventType": "ACR_TUNER_DATA",
    "timestamp": 1709568000000
  },
  "EventData": {
    "channelData": {"majorId": 45, "minorId": 1},
    "programData": {"programId": "EP012345678901", "startTime": 1709564400}
  }
}
```

Response: Pydantic model with status and event ID.

Every endpoint has a typed Pydantic `response_model`. Every request/response model includes `json_schema_extra` examples for Swagger UI.

Error responses:

```json
{
  "error": "TvEventsSecurityValidationError",
  "message": "Security hash decryption failure for tvid=ITV00C000000000000001.",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### `/ops/*` Endpoints

All return typed Pydantic models. Diagnostic endpoints (GET) require no auth (internal network only). Remediation endpoints (POST/PUT) log all mutations.

## Observability & SRE

**Embedded Monitoring Removal:** The legacy codebase contains `pygerduty` (PagerDuty SDK) and references to `google-cloud-monitoring` (Stackdriver). These are intentionally dropped. The rebuilt application emits standardized telemetry via OpenTelemetry — metrics, traces, and structured JSON logs — and exposes `/ops/*` diagnostic endpoints. Alerting, paging, and dashboard integrations are handled externally by the SRE agent and the monitoring stack.

**Golden Signals (middleware-collected):**
- Latency: p50, p95, p99 per endpoint (histogram)
- Traffic: requests/second per endpoint (counter)
- Errors: error rate per endpoint and error type (counter)
- Saturation: Kafka producer queue depth, RDS connection pool utilization, Redis connection pool utilization

**RED Metrics:**
- Rate: requests/second by endpoint and event type
- Errors: 4xx + 5xx by endpoint and error category
- Duration: request duration histogram by endpoint

**SLOs:**
- Availability: 99.9% (measured by successful responses / total requests)
- Latency: p99 < 200ms (event ingestion end-to-end)
- Error rate: < 0.1% of requests return 5xx

**OTEL Export:** OTLP gRPC to OTEL Collector sidecar. Structured JSON logs with trace correlation (`trace_id`, `span_id`).

## Auth & RBAC

- **TV clients**: HMAC security hash validated on POST `/v1/events`. Hash computed from `tvid` + salt using `hmac.compare_digest()` for constant-time comparison. Salt loaded from AWS Secrets Manager (via `T1_SALT` env var injected by EKS secret store).
- **Internal /ops/***: Network-level restriction (not exposed via Kong). No additional auth required for diagnostics. Remediation endpoints logged with caller IP.
- **Service-to-service**: IAM roles scoped per service — Kafka producer role, RDS read-only role, Redis access role.
- **Audit logging**: All `/ops/*` POST/PUT operations logged with timestamp, caller, action, and parameters.

## External Dependencies & Contracts

| Dependency | Type | Direction | Interface | Contract Status | Inside/Outside | Fallback | SLA | Integration Tests |
|---|---|---|---|---|---|---|---|---|
| AWS RDS PostgreSQL | Managed service | Outbound | asyncpg TCP | Documented (query below) | Outside | Redis cache → empty list | 99.95% (AWS SLA) | Query format validation |
| Apache Kafka | Managed service | Outbound | confluent-kafka producer | Documented (topic schema = legacy JSON format) | Inside | Dead-letter topic + local retry | 99.9% | Message delivery verification |
| Redis | Managed service | Outbound | rebuilder-redis-module | Documented (module API) | Inside | RDS fallback | 99.9% | Get/set/TTL behavior |
| Kong API Gateway | Infrastructure | Inbound | HTTP reverse proxy | Documented (route config) | Outside | N/A | 99.99% | N/A |
| AWS Secrets Manager | Managed service | Outbound | AWS SDK / env injection | Documented (`T1_SALT`) | Outside | Fail startup | 99.99% | Secret retrieval |
| Vizio SmartCast TVs | External client | Inbound | HTTP POST | Documented (payload schema above) | Outside | N/A | N/A | Payload validation tests |

**RDS Contract:**
```sql
SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map;
```
Returns: list of string `channel_id` values.

Unknown inbound consumers beyond TVs — **risk**. Mitigation: output JSON format is preserved exactly, `/v1/events` maintains backward-compatible response shapes.

## Data Migration Plan

**No database migration.** The application is read-only against RDS. The table structure is unchanged.

**Cache migration:** File-based → Redis. No data migration — cache is populated from RDS on startup and refreshed via TTL.

**Event format:** Flattened JSON output format is preserved byte-for-byte. Golden-file tests validate against captured legacy output:

| Field | Type | Source | Notes |
|---|---|---|---|
| `tvid` | string | `TvEvent.tvid` | Direct copy |
| `client` | string | `TvEvent.client` | Direct copy |
| `tvevent_timestamp` | number | `TvEvent.timestamp` | Renamed |
| `tvevent_eventtype` | string | `TvEvent.EventType` | Renamed |
| `zoo` | string | Environment var | `FLASK_ENV` equivalent |
| `channelid` | string/int | `EventData.channelData.majorId` (flattened) | Obfuscated if blacklisted |
| `programid` | string | `EventData.programData.programId` (flattened) | Obfuscated if blacklisted |
| `namespace` | string | Event type specific | From event handler |
| `appid` | string | Event type specific | From event handler |
| `*` | various | `EventData.*` | Flattened with key prefix |

## Rollout Plan

1. **Dev**: Auto-deploy on merge to `main`. Full test suite + Terraform plan on PR.
2. **Staging**: Manual promotion after dev validation. Integration tests with real Kafka/RDS/Redis.
3. **Shadow production**: Mirror traffic to both legacy and new services. Compare Kafka output with Firehose records.
4. **Canary production**: Kong routes 5% → 25% → 50% → 100% traffic to new service.
5. **Full production**: Decommission legacy service after 2-week validation period.
6. **Feature flags**: `KAFKA_DELIVERY_ENABLED`, `LEGACY_FIREHOSE_BRIDGE_ENABLED` for gradual transition.

## Success Criteria

1. All unit tests pass (≥80% coverage)
2. Output JSON format matches legacy byte-for-byte for all event types (golden-file tests)
3. HMAC validation accepts all valid TV requests and rejects invalid ones (tested against production-like data)
4. Kafka delivery achieves at-least-once semantics with < 0.01% message loss
5. p99 latency < 200ms under production load (300–500 pods)
6. `/ops/metrics` returns real Golden Signals and RED metrics
7. Zero critical/high CVEs in dependency audit
8. All Phase 1 compliance checks from skill.md pass

## ADRs Required

1. **ADR-001**: Use Python 3.12 / FastAPI as backend framework
2. **ADR-002**: Use Apache Kafka for event delivery (replacing Kinesis Firehose)
3. **ADR-003**: Use PostgreSQL via asyncpg (keep existing RDS)
4. **ADR-004**: Use Redis via standalone rebuilder-redis-module for caching
5. **ADR-005**: Standalone HMAC validation (replacing cnlib token_hash)
6. **ADR-006**: Use Terraform for infrastructure-as-code
7. **ADR-007**: Stay on AWS (no cloud migration)
8. **ADR-008**: Use OTEL Collector for observability (removing embedded PagerDuty/New Relic)

## Open Questions

1. **HMAC implementation details**: What hash algorithm and salt preprocessing does `cnlib.token_hash.security_hash_match` use? The cnlib submodule is empty — we need to verify against production data or get the implementation details from the cntools team.
2. **Kafka topic naming and partitioning**: What topic naming convention should be used? How many partitions for the event topic to support 300–500 pod throughput?
3. **Downstream consumer readiness**: Which downstream pipelines consume from the Firehose-delivered S3 path? Are they ready to switch to Kafka-sourced delivery?
4. **Redis cluster sizing**: What instance type and cluster size for production Redis supporting 300–500 pods?
