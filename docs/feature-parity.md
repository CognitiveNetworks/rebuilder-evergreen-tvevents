# Feature Parity Matrix

> Complete list of every user-facing feature, integration, and workflow in the legacy tvevents-k8s application.
> Each feature gets a status. The rebuild is not complete until every **Must Rebuild** and **Rebuild Improved** feature passes acceptance testing.

## Features

| Feature | Legacy Behavior | Status | Target Behavior | Acceptance Criteria | Notes |
|---|---|---|---|---|---|
| POST / ingestion endpoint | Receives TV event JSON payload, validates, transforms, delivers to Firehose | Must Rebuild | Same flow with FastAPI, Pydantic models, Kafka delivery | POST with valid payload returns 200 "OK", event delivered to Kafka topic | Core ingestion path |
| GET /status health check | Returns "OK" regardless of dependency health | Rebuild Improved | Returns "OK" for backward compat; `/ops/status` provides real health verdict | GET /status returns 200 "OK"; GET /ops/status returns dependency-aware verdict | Legacy compat preserved |
| GET /health endpoint | Does not exist in legacy | Rebuild Improved | Alias for /status | GET /health returns 200 "OK" | New endpoint |
| HMAC hash validation | `MD5(tvid + T1_SALT)` via cnlib.token_hash, uses `==` comparison | Rebuild Improved | Same hash computation, `hmac.compare_digest()` for constant-time comparison | Valid hash accepted, invalid hash rejected; timing-safe comparison verified | Security fix — see ADR-006 |
| Region-based hash algorithm | MD5 for US, SHA-256 for EU (`eu-west-1`) | Must Rebuild | Same region-based selection via `AWS_REGION` environment variable | SHA-256 used when `AWS_REGION=eu-west-1`, MD5 otherwise | Preserves EU compatibility |
| Required parameter validation | Checks tvid, client, h, EventType, timestamp in request args and payload | Must Rebuild | Same validation logic, returns 400 with structured error on failure | Missing required param returns 400 with error message | Port directly |
| Parameter consistency check | Verifies tvid and event_type match between URL args and payload | Must Rebuild | Same check | Mismatched tvid/event_type returns 400 | Port directly |
| Timestamp validation | Verifies timestamp is valid Unix timestamp in milliseconds | Must Rebuild | Same validation | Invalid timestamp returns 400 | Port directly |
| ACR_TUNER_DATA event type | Validates channelData/programData or Heartbeat, converts programdata_starttime s→ms | Must Rebuild | Same validation and conversion via event type dispatch | ACR_TUNER_DATA with valid channelData processes correctly; Heartbeat accepted | Port directly |
| NATIVEAPP_TELEMETRY event type | Validates Timestamp field, extracts Namespace and AppId | Must Rebuild | Same validation and extraction | NATIVEAPP_TELEMETRY with valid Timestamp processes correctly | Port directly |
| PLATFORM_TELEMETRY event type | JSON Schema validation, PanelState uppercase normalization | Must Rebuild | Same validation (jsonschema) and normalization | PLATFORM_TELEMETRY with valid PanelData processes correctly; PanelState uppercased | Port directly |
| Event type dispatch | `event_type_map` dict dispatching to per-type validate/output functions | Must Rebuild | Same dispatch pattern with per-type classes or functions | Each event type dispatches to correct handler | Port pattern directly |
| Payload flattening | Unwraps TvEvent, lowercases keys, merges EventData fields | Must Rebuild | Same flattening logic | Output JSON matches legacy flat format | Port directly |
| Output JSON generation | Per-event-type output generation with metadata (zoo, timestamp, eventtype) | Must Rebuild | Same output format with same metadata fields | Output JSON identical to legacy for same input | Port directly |
| Channel blacklist obfuscation | Obfuscates channelid, programid, channelname if channel is blacklisted or isContentBlocked=true | Must Rebuild | Same obfuscation logic | Blacklisted channel fields replaced with "OBFUSCATED" | Port directly |
| Blacklist file cache | JSON array at `/tmp/.blacklisted_channel_ids_cache`, populated from RDS at startup | Must Rebuild | Same file path, same format, same population logic | Cache file created at startup, read on first request | Preserve — see ADR-005 |
| Blacklist RDS fallback | If file cache missing/unreadable, query RDS and rebuild cache | Must Rebuild | Same fallback via standalone RDS module | Cache miss triggers RDS query and file write | Port directly |
| Firehose delivery | Delivers output to up to 4 Firehose streams via cnlib in parallel | Rebuild Improved | Delivers to Kafka topics via standalone Kafka module | Events delivered to configured Kafka topics | Kafka replaces Firehose — see ADR-002 |
| Debug stream routing | Sends pre-obfuscation data to debug streams when TVEVENTS_DEBUG=true | Must Rebuild | Same routing to debug Kafka topics | Debug topic receives pre-obfuscation data when debug enabled | Map Firehose streams to Kafka topics |
| Evergreen/Legacy stream split | Separate delivery to evergreen and legacy streams controlled by SEND_EVERGREEN/SEND_LEGACY | Must Rebuild | Same split controlled by environment variables, mapped to Kafka topics | Events routed to correct topics based on env vars | Port directly |
| Error handling | TvEventsCatchallException with status_code=400, logged with traceback | Rebuild Improved | FastAPI exception handlers with structured JSON error responses | Errors return structured JSON with error type and message | Improved error format |
| OTEL tracing | Manual spans for DB, cache, event type, delivery operations | Rebuild Improved | OTEL auto-instrumentation + manual spans for business logic only | Traces visible in New Relic with correct span hierarchy | Auto-instrumentation — see ADR-004 |
| OTEL metrics | Counters (request, DB, cache, event validation) and histograms (DB query duration) | Rebuild Improved | Golden Signals + RED metrics via middleware, exposed at /ops/metrics | Metrics available at /ops/metrics and exported via OTLP | Improved metrics model |
| OTEL logging | LoggerProvider + OTLPLogExporter bridge | Must Rebuild | Structured JSON logging with OTEL trace correlation | Logs contain trace_id, span_id; exported via OTLP | Port with auto-instrumentation |
| /ops/* diagnostic endpoints | Do not exist in legacy | Rebuild Improved | /ops/status, /ops/health, /ops/metrics, /ops/config, /ops/dependencies, /ops/errors | All 6 diagnostic endpoints return structured responses | New — required by service bootstrap |
| /ops/* remediation endpoints | Do not exist in legacy | Rebuild Improved | /ops/drain, /ops/cache/flush, /ops/circuits, /ops/loglevel, /ops/scale | All 5 remediation endpoints functional | New — required by service bootstrap |
| Graceful shutdown | Does not exist in legacy — no drain mechanism | Rebuild Improved | Drain flag via /ops/drain, health returns 503 during drain, connection cleanup | /ops/drain sets drain; /ops/status returns unhealthy; connections closed | New |
| OpenAPI spec | Does not exist in legacy | Rebuild Improved | Auto-generated by FastAPI with Pydantic models and json_schema_extra examples | Swagger UI at /docs with typed schemas and example payloads | New — see ADR-001 |

### Status Definitions

- **Must Rebuild** — feature must exist in the target with equivalent behavior
- **Rebuild Improved** — feature will be rebuilt with specific improvements
- **Intentionally Dropped** — feature will not be rebuilt (requires documented justification below)
- **Deferred** — feature will be rebuilt in a later phase

## Intentionally Dropped — Justifications

| Feature | Justification |
|---|---|
| cnlib.firehose.Firehose | Replaced by standalone Kafka module (rebuilder-kafka-module). Firehose delivery is replaced by Kafka delivery per platform migration mandate — see ADR-002 |
| cnlib.token_hash | Replaced by inline `security.py` module with `hmac.compare_digest()` — see ADR-006 |
| cnlib.log.getLogger | Replaced by standard Python `logging.getLogger()`. cnlib.log was a thin wrapper with no additional functionality used by this service |
| gevent worker model | Replaced by Uvicorn ASGI server. FastAPI uses asyncio, not gevent — see ADR-001 |
| Unused dependencies (boto v2, google-cloud-monitoring, pymemcache, PyMySQL, pyzmq, redis, fakeredis, python-consul, pygerduty) | Not imported by any application code. Removed to reduce container image size and attack surface |
| Google Cloud Monitoring client | Embedded vendor-specific monitoring removed per PRD §Observability & SRE. Monitoring handled via OTEL + external platform |
| pygerduty (PagerDuty SDK) | Embedded alerting client removed per PRD §Observability & SRE. Alerting is an infrastructure concern handled by the SRE agent |

## Integrations

| Integration | Legacy Mechanism | Status | Target Mechanism | Notes |
|---|---|---|---|---|
| AWS Kinesis Data Firehose | cnlib.firehose.Firehose (boto3 put_record_batch) | Intentionally Dropped | Apache Kafka via standalone rebuilder-kafka-module | Platform migration — see ADR-002 |
| AWS RDS PostgreSQL | psycopg2 direct connection in dbhelper.py | Rebuild Improved | psycopg2 via standalone rebuilder-rds-module with connection pooling and retry | See ADR-003 |
| New Relic (OTEL) | Manual OTEL SDK with OTLP HTTP exporters | Rebuild Improved | OTEL auto-instrumentation with same OTLP HTTP exporters | See ADR-004 |
| Vizio Smart TVs (inbound) | Flask POST / endpoint | Must Rebuild | FastAPI POST / endpoint with Pydantic models | Backward-compatible payload format |
| Kubernetes probes | GET /status:8000 | Must Rebuild | GET /status:8000 (same) | Same health check path and port |

## Library Transitions

| Legacy Library | Legacy Function/Module | Target Replacement | Confirmed |
|---|---|---|---|
| cnlib | `cnlib.firehose.Firehose` | `rebuilder-kafka-module` `KafkaProducerClient` | Yes — module created in `output/rebuilder-kafka-module/` |
| cnlib | `cnlib.firehose.Firehose.send_records()` | `KafkaProducerClient.produce()` | Yes — produce method in `src/kafka_module/producer.py` |
| cnlib | `cnlib.token_hash.security_hash_match()` | `src/tvevents/domain/security.py` `security_hash_match()` | Yes — uses `hmac.compare_digest()` |
| cnlib | `cnlib.token_hash.security_hash_token()` | `src/tvevents/domain/security.py` `security_hash_token()` | Yes — same algorithm, standard library only |
| cnlib | `cnlib.log.getLogger()` | `logging.getLogger()` (Python standard library) | Yes — drop-in replacement |
| Flask | `flask.Flask` | `fastapi.FastAPI` | Yes |
| Flask | `flask.Blueprint` | `fastapi.APIRouter` | Yes |
| Flask | `flask.request` | FastAPI dependency injection (`Request`) | Yes |
| Flask | `FlaskInstrumentor` | `opentelemetry-instrumentation-fastapi` (auto) | Yes |
| Gunicorn + gevent | `gunicorn -k gevent` | `uvicorn` (ASGI) | Yes |
