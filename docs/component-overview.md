# Component Overview — tvevents-k8s

## Service Summary

`tvevents-k8s` is a stateless TV event ingestion microservice that receives smart TV telemetry payloads via HTTP POST, validates and transforms them, and delivers the output to Apache Kafka topics for downstream consumption.

## Component Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │              tvevents-k8s                    │
                    │                                             │
  HTTP POST ───────►│  routes.py ──► validation.py                │
  (TV payload)      │       │        security.py                  │
                    │       │        event_types.py                │
                    │       ▼                                     │
                    │  transform.py ──► obfuscation.py            │
                    │       │              │                      │
                    │       │        cache.py ◄── database.py     │
                    │       │        (file)       (RDS)           │
                    │       ▼                                     │
                    │  delivery.py ──────────────────────►  Kafka │
                    │                                             │
                    │  ops.py (diagnostics / remediation)         │
                    │  metrics.py (Golden Signals / RED)          │
                    └─────────────────────────────────────────────┘
```

## Module Responsibilities

### API Layer (`src/tvevents/api/`)

| Module | Responsibility |
|--------|---------------|
| `routes.py` | POST `/` ingestion, GET `/status`, GET `/health` |
| `ops.py` | `/ops/*` diagnostic and remediation endpoints |
| `models.py` | Pydantic v2 request/response models with OpenAPI examples |

### Domain Layer (`src/tvevents/domain/`)

| Module | Responsibility |
|--------|---------------|
| `security.py` | HMAC hash generation and constant-time comparison (replaces `cnlib.token_hash`) |
| `validation.py` | Required parameter checks, timestamp validation, security hash verification |
| `event_types.py` | Event type dispatch map, per-type validation and output generation |
| `transform.py` | JSON flattening, namespace extraction, output JSON assembly |
| `obfuscation.py` | Channel blacklist check and field obfuscation |
| `delivery.py` | Kafka producer singleton, topic delivery, flush/close lifecycle |

### Infrastructure Layer (`src/tvevents/infrastructure/`)

| Module | Responsibility |
|--------|---------------|
| `cache.py` | File-based blacklist cache (read/write/flush) at `/tmp/.blacklisted_channel_ids_cache` |
| `database.py` | PostgreSQL client via `psycopg2` — blacklisted channel ID lookup, health check |

### Cross-cutting

| Module | Responsibility |
|--------|---------------|
| `config.py` | `pydantic-settings` environment configuration with validation |
| `deps.py` | Singleton holders for RDS client and blacklist cache |
| `main.py` | FastAPI app factory, lifespan hooks, middleware registration |
| `middleware/metrics.py` | Request-level metrics collection (Golden Signals, RED method) |

## Request Flow

1. **Receive** — FastAPI route handler receives POST `/` with JSON body
2. **Validate** — Required params, HMAC security hash, event-type-specific schema
3. **Transform** — Flatten nested JSON, merge TvEvent + EventData, set zoo/namespace
4. **Obfuscate** — Check `iscontentblocked` flag and blacklist cache; replace channel fields if needed
5. **Deliver** — Send to configured Kafka topics via `confluent-kafka` producer
6. **Respond** — Return `{"status": "OK"}` or structured error

## Dependencies

| Dependency | Purpose | Connection |
|-----------|---------|------------|
| PostgreSQL (AWS RDS) | Blacklisted channel ID lookup | `psycopg2` direct connection |
| Apache Kafka (AWS MSK) | Event delivery | `confluent-kafka` producer |
| New Relic (OTLP) | Observability | OTEL auto-instrumentation |

## Configuration

All configuration via environment variables through `pydantic-settings`. See [`.env.example`](../.env.example) for the complete list.

## Operational Endpoints

Full `/ops/*` endpoint suite for SRE agent integration:
- Diagnostics: status, health, metrics, config, dependencies, errors, circuits
- Remediation: drain, cache/flush, loglevel, scale
