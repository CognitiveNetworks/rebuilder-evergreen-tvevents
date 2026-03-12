# Observability — evergreen-tvevents

## Overview

This service instruments two distinct types of metrics. Understanding the
difference is critical for incident response and capacity planning.

| Dimension | Service Metrics (platform-managed) | Application Metrics (app-instrumented) |
|---|---|---|
| **Collected by** | Cloud platform (GKE / Cloud Run) | In-process middleware + OTEL SDK |
| **Examples** | CPU %, memory %, instance count, network I/O | Latency p50/p95/p99, error rate, request rate |
| **Persistence** | Weeks–months in Cloud Monitoring | In-memory (resets on restart); OTEL export persists in backend |
| **Query method** | `gcloud monitoring` / Cloud Console | `curl /ops/metrics` (pull) or OTEL exporter (push) |
| **When to use** | Scaling decisions, resource alerts | SLO tracking, incident triage, capacity modeling |

---

## Golden Signals

The service reports [Google SRE Golden Signals](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals):

| Signal | Source | Endpoint field |
|---|---|---|
| **Latency** | Per-request timer in `metrics_middleware` | `latency_p50_ms`, `latency_p95_ms`, `latency_p99_ms` |
| **Traffic** | Incrementing counter per request | `request_rate_per_sec` |
| **Errors** | Counter per 4xx/5xx response | `error_rate_pct` |
| **Saturation** | Placeholder for connection-pool / queue depth | `saturation_pct` |

## RED Method

The `/ops/metrics` endpoint also surfaces the RED method breakdown:

| Metric | Description |
|---|---|
| **Rate** | Requests per second (total) |
| **Errors** | Error percentage over lifetime |
| **Duration** | p50 / p95 / p99 latency in milliseconds |

---

## Application Metrics — Querying `/ops/metrics`

### Example: pull current Golden Signals

```bash
curl -s http://localhost:8000/ops/metrics | jq .golden_signals
```

```json
{
  "latency_p50_ms": 2.1,
  "latency_p95_ms": 8.4,
  "latency_p99_ms": 15.7,
  "request_rate_per_sec": 142.3,
  "error_rate_pct": 0.02,
  "saturation_pct": 0.0
}
```

### Example: pull RED metrics

```bash
curl -s http://localhost:8000/ops/metrics | jq .red
```

```json
{
  "rate": 142.3,
  "errors": 0.02,
  "duration_p50_ms": 2.1,
  "duration_p95_ms": 8.4,
  "duration_p99_ms": 15.7
}
```

### Example: composite health verdict

```bash
curl -s http://localhost:8000/ops/status | jq .
```

Returns `healthy`, `degraded`, or `unhealthy` based on error rate, p99 latency,
and dependency health.

---

## Service Metrics — Querying the Platform

### GKE / Cloud Monitoring

```bash
# CPU utilization for the service over the last hour
gcloud monitoring time-series list \
  --project=PROJECT_ID \
  --filter='metric.type="kubernetes.io/container/cpu/core_usage_time" AND resource.labels.container_name="evergreen-tvevents"' \
  --interval-start-time="$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --format=json | jq '.[0].points[:5]'

# Memory utilization
gcloud monitoring time-series list \
  --project=PROJECT_ID \
  --filter='metric.type="kubernetes.io/container/memory/used_bytes" AND resource.labels.container_name="evergreen-tvevents"' \
  --interval-start-time="$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --format=json | jq '.[0].points[:5]'

# Request count (if using Cloud Run or GKE ingress)
gcloud monitoring time-series list \
  --project=PROJECT_ID \
  --filter='metric.type="loadbalancing.googleapis.com/https/request_count" AND resource.labels.url_map_name="evergreen-tvevents"' \
  --interval-start-time="$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --format=json
```

---

## OTEL Instrumentation

| Component | Configuration |
|---|---|
| **Tracer** | `TracerProvider` → OTLP HTTP exporter (`OTEL_EXPORTER_OTLP_ENDPOINT`) |
| **Meter** | `MeterProvider` → `PeriodicExportingMetricReader` (30 s interval) |
| **Logger** | `LoggerProvider` → `BatchLogRecordProcessor` → OTLP exporter |
| **Auto-instrumentation** | `FastAPIInstrumentor.instrument_app()` for span-per-request |
| **Compression** | gzip (`OTEL_EXPORTER_OTLP_COMPRESSION=gzip`) |

### Custom Metrics

| Metric name | Type | Description |
|---|---|---|
| `send_request_counter` | Counter | Total event-processing requests |
| `metrics_middleware` latency | In-memory deque | Per-request latency samples (max 10 000) |

### Collector (local development)

The `otel-collector-config.yaml` runs a local OTEL Collector with:
- **Receivers:** OTLP gRPC (4317), OTLP HTTP (4318)
- **Processor:** Batch (5 s timeout, 1024 batch size)
- **Exporter:** Debug (verbose) — swap for Stackdriver / Cloud Trace in production

---

## Structured Logging

All logs are structured JSON to stdout via `cnlib.log`. Health-check paths
(`/status`, `/health`, `/ops/health`) are excluded from request logging to
reduce noise. Log level is changeable at runtime:

```bash
curl -X POST http://localhost:8000/ops/log-level -H 'Content-Type: application/json' -d '{"level": "DEBUG"}'
```

---

## `/ops/*` Endpoint Reference

### Diagnostics

| Endpoint | Method | Purpose |
|---|---|---|
| `/ops/status` | GET | Composite health verdict (healthy / degraded / unhealthy) |
| `/ops/health` | GET | Deep dependency check (Kafka, RDS, cache) with per-dep latency |
| `/ops/metrics` | GET | Golden Signals + RED metrics |
| `/ops/config` | GET | Runtime configuration (non-sensitive) |
| `/ops/dependencies` | GET | External dependency status |
| `/ops/cache` | GET | Blacklist cache statistics |
| `/ops/errors` | GET | Recent error summary by type |

### Remediation

| Endpoint | Method | Purpose |
|---|---|---|
| `/ops/drain` | POST | Enable / disable drain mode |
| `/ops/cache/refresh` | POST | Trigger blacklist cache refresh |
| `/ops/cache/flush` | POST | Alias for refresh |
| `/ops/circuits` | POST | Circuit breaker status |
| `/ops/log-level` | POST | Change runtime log level |

All remediation endpoints are idempotent and non-destructive.
