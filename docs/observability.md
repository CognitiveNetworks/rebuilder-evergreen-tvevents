# Observability — tvevents-k8s

## Strategy

OTEL auto-instrumentation via `opentelemetry-instrument` CLI wrapper. No manual span creation except for business-logic-level tracing (e.g., event type validation, Kafka delivery).

## Instrumentation Stack

| Layer | Library | Auto-instrumented |
|-------|---------|-------------------|
| HTTP Server | `opentelemetry-instrumentation-fastapi` | Yes |
| HTTP Client | `opentelemetry-instrumentation-httpx` | Yes |
| PostgreSQL | `opentelemetry-instrumentation-psycopg2` | Yes |
| Logging | `opentelemetry-instrumentation-logging` | Yes |

## Exporter

- **Protocol**: OTLP/gRPC
- **Endpoint**: `https://otlp.nr-data.net:443` (New Relic)
- **Authentication**: `api-key` header via `OTEL_EXPORTER_OTLP_HEADERS`

## Service Identity

```
OTEL_SERVICE_NAME=tvevents-k8s
OTEL_RESOURCE_ATTRIBUTES=service.version=0.1.0,deployment.environment=${ENV}
```

## Metrics

### Application Metrics (via `/ops/metrics`)

**Golden Signals:**
- `latency_p50_ms`, `latency_p95_ms`, `latency_p99_ms`
- `traffic_total_requests`
- `errors_total`, `errors_by_status`
- `saturation_in_flight`

**RED Method:**
- `rate_total`
- `errors_ratio`
- `duration_p50_ms`, `duration_p95_ms`, `duration_p99_ms`

### OTEL Auto-generated Metrics

- `http.server.duration` — request latency histogram
- `http.server.request.size` — request body size
- `http.server.response.size` — response body size
- `http.server.active_requests` — in-flight gauge

## Traces

Every inbound HTTP request generates a trace with spans for:
1. FastAPI route handler
2. psycopg2 database queries (blacklist lookup)
3. Kafka produce calls

## Logs

Structured JSON logs via Python `logging` module, correlated with OTEL trace IDs when auto-instrumentation is active.

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`
Runtime change: `POST /ops/loglevel {"level": "DEBUG"}`

## Health Checks

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `GET /status` | Liveness probe | Kubernetes |
| `GET /health` | Liveness probe alias | Kubernetes |
| `GET /ops/status` | Composite health verdict | SRE agent |
| `GET /ops/health` | Dependency-aware check | SRE agent |

## Alerts (New Relic)

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Error Rate | `errors_ratio > 0.01` for 5 min | P2 |
| High Latency | `latency_p99_ms > 500` for 5 min | P3 |
| Dependency Down | `/ops/health` status = degraded for 3 min | P2 |
| Pod Restart Loop | `restartCount > 3` in 10 min | P1 |

## Collector Configuration

See [`otel-collector-config.yaml`](../otel-collector-config.yaml) for the OTEL Collector sidecar configuration.
