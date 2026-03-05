# Observability — rebuilder-evergreen-tvevents

## Overview

The service produces **two distinct categories** of metrics:

| Category | Source | Scope | Lifetime |
|---|---|---|---|
| **Service metrics (platform)** | AWS EKS / CloudWatch | Infrastructure: CPU, memory, network, request count | Weeks to months (CloudWatch retention) |
| **Application metrics (app)** | `MetricsMiddleware` inside the process | Business logic: Golden Signals, RED, per-endpoint breakdown | In-process counters reset on restart; OTEL-exported data persists in the collector backend |

Both are necessary. Platform metrics tell you whether the **infrastructure** is healthy; application metrics tell you whether the **service behaviour** is correct.

---

## Service Metrics (Platform-Managed)

These are collected automatically by AWS EKS and CloudWatch. No application code is involved.

### What They Measure

| Metric | Description | Unit |
|---|---|---|
| CPU utilisation | Pod CPU usage vs. requested/limit | Percent |
| Memory utilisation | Pod RSS vs. requested/limit | Bytes / Percent |
| Request count | ALB-level request count to the target group | Count |
| Request latency | ALB target response time | Milliseconds |
| Instance count | Number of running pods (Deployment replicas) | Count |
| Network I/O | Bytes in/out per pod | Bytes/sec |

### How to Query

**CloudWatch Metrics Insights** (namespace: `ContainerInsights`, cluster: your EKS cluster name):

```sql
-- Average CPU utilisation over 5 minutes for the tvevents pods
SELECT AVG(pod_cpu_utilization)
FROM SCHEMA("ContainerInsights", ClusterName, Namespace, PodName)
WHERE ClusterName = 'your-eks-cluster'
  AND Namespace = 'tvevents'
GROUP BY PodName
ORDER BY AVG(pod_cpu_utilization) DESC
```

```sql
-- Memory utilisation
SELECT AVG(pod_memory_utilization)
FROM SCHEMA("ContainerInsights", ClusterName, Namespace, PodName)
WHERE ClusterName = 'your-eks-cluster'
  AND Namespace = 'tvevents'
GROUP BY PodName
```

```sql
-- ALB request count and latency (namespace: AWS/ApplicationELB)
SELECT SUM(RequestCount), AVG(TargetResponseTime)
FROM SCHEMA("AWS/ApplicationELB", TargetGroup, LoadBalancer)
WHERE TargetGroup = 'your-target-group'
```

### Typical Dashboards

- **EKS Pod Overview** — CPU, memory, restart count, pod readiness per deployment.
- **ALB Target Group** — request count, 4xx/5xx rates, target response time.
- **Node-level** — node CPU/memory to detect noisy-neighbour or scheduling issues.

---

## Application Metrics (In-Process)

These are collected by the `MetricsMiddleware` (Starlette middleware defined in `src/tvevents/middleware/metrics.py`). The middleware intercepts every HTTP request and records:

- **Method and path** (e.g. `POST /v1/events`)
- **HTTP status code**
- **Duration** in milliseconds (measured with `time.monotonic()`)
- **Error type** (Python exception class name, if any)

Data is stored in the `MetricsCollector` singleton (thread-safe, in-memory). Counters and duration lists **reset when the process restarts**.

### Golden Signals

| Signal | Field | Description |
|---|---|---|
| **Latency** | `latency.p50`, `latency.p95`, `latency.p99` | Request duration percentiles in ms |
| **Traffic** | `traffic_total`, `traffic_per_sec` | Total request count and per-second rate |
| **Errors** | `error_count`, `error_rate` | Total 4xx/5xx count and ratio to total |
| **Saturation** | `saturation.rds_pool` (and others) | Resource utilisation ratio (0.0–1.0) |

### RED Method

| Dimension | Field | Description |
|---|---|---|
| **Rate** | `rate` | Requests per second (since process start) |
| **Errors** | `errors` | Error ratio (0.0–1.0) |
| **Duration** | `duration_p50`, `duration_p95`, `duration_p99` | Latency percentiles in ms |

RED metrics are also computed **per endpoint** in the `by_endpoint` map.

---

## `/ops/metrics` Endpoint

Pull-based access to live application metrics.

### Request

```bash
curl -s http://localhost:8000/ops/metrics | python -m json.tool
```

### Sample Response

```json
{
    "golden_signals": {
        "latency": {
            "p50": 3.2,
            "p95": 12.8,
            "p99": 45.1
        },
        "traffic_total": 1048576,
        "traffic_per_sec": 892.4,
        "error_count": 127,
        "error_rate": 0.00012,
        "saturation": {
            "rds_pool": 0.32
        }
    },
    "red": {
        "rate": 892.4,
        "errors": 0.00012,
        "duration_p50": 3.2,
        "duration_p95": 12.8,
        "duration_p99": 45.1
    },
    "by_endpoint": {
        "POST /v1/events": {
            "rate": 890.1,
            "errors": 0.00011,
            "duration_p50": 3.1,
            "duration_p95": 12.5,
            "duration_p99": 44.8
        }
    }
}
```

### Notes

- The endpoint also updates saturation data (e.g. RDS connection pool utilisation) before returning.
- All latency values are in **milliseconds**.
- `error_rate` and `errors` are ratios (0.0–1.0), not counts.
- Data resets on process restart. For persistent history, rely on OTEL export.

---

## OTEL Export (Push-Based)

The service pushes traces, metrics, and logs to an OpenTelemetry Collector via OTLP gRPC.

### Bootstrap

OTEL is initialised in `src/tvevents/main.py` → `_configure_otel()` during the lifespan startup:

1. A `Resource` is created with `service.name`, `service.version`, and `deployment.environment`.
2. **Traces** — `OTLPSpanExporter` → `BatchSpanProcessor` → `TracerProvider`.
3. **Metrics** — `OTLPMetricExporter` → `PeriodicExportingMetricReader` → `MeterProvider`.
4. **Logs** — `OTLPLogExporter` → `BatchLogRecordProcessor` → `LoggerProvider` (attached to the Python root logger).
5. `FastAPIInstrumentor.instrument_app(app)` adds automatic span creation for every request.

### Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint for the collector |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Trace sampling ratio (1.0 = 100%, 0.1 = 10%) |

### Collector Pipeline

The OTEL Collector is configured in `otel-collector-config.yaml`:

```
Receivers:  otlp (gRPC :4317, HTTP :4318)
     │
Processors: batch (timeout 5s, batch size 1024)
     │
Exporters:  debug (local dev), otlp/newrelic (production)
```

All three signal types (traces, metrics, logs) follow the same pipeline.

### Docker Compose

The collector runs as a sidecar in `docker-compose.yml`:

```yaml
otel-collector:
  image: otel/opentelemetry-collector-contrib:0.113.0
  ports:
    - "4317:4317"   # OTLP gRPC
    - "4318:4318"   # OTLP HTTP
  volumes:
    - ./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml
```

In production (EKS), the collector runs as a DaemonSet or sidecar container in the same pod.

---

## When to Use Which

| Question | Use | Why |
|---|---|---|
| Is the pod running out of CPU/memory? | **Platform** (CloudWatch) | Infrastructure-level, not visible to the app |
| Are we scaling correctly? | **Platform** (pod count, HPA metrics) | Kubernetes scheduler metrics |
| What is p99 latency for `POST /v1/events`? | **Application** (`/ops/metrics` or OTEL) | Per-endpoint percentile breakdown |
| What is the error rate right now? | **Application** (`/ops/metrics`) | Real-time, no query delay |
| Did error rate spike at 3 AM last Tuesday? | **OTEL** (exported metrics in backend) | Historical data persists beyond restarts |
| Is the ALB routing traffic correctly? | **Platform** (ALB metrics) | Network layer, outside the app |
| Is the RDS connection pool saturated? | **Application** (`saturation.rds_pool`) | App-level resource tracking |
| Is the node over-committed? | **Platform** (node CPU/memory) | Scheduling and capacity planning |

---

## Example Queries

### Platform: CloudWatch — Pod CPU Spike

```sql
SELECT MAX(pod_cpu_utilization)
FROM SCHEMA("ContainerInsights", ClusterName, Namespace, PodName)
WHERE ClusterName = 'your-eks-cluster'
  AND Namespace = 'tvevents'
  AND PodName LIKE 'tvevents-api%'
ORDER BY MAX(pod_cpu_utilization) DESC
LIMIT 5
```

### Platform: CloudWatch — ALB 5xx Rate

```sql
SELECT SUM(HTTPCode_Target_5XX_Count) / SUM(RequestCount) AS error_rate
FROM SCHEMA("AWS/ApplicationELB", TargetGroup, LoadBalancer)
WHERE TargetGroup = 'your-target-group'
```

### Application: Live Metrics via curl

```bash
# Golden signals + RED for all endpoints
curl -s http://localhost:8000/ops/metrics | python -m json.tool

# Just the p99 latency
curl -s http://localhost:8000/ops/metrics | python -c "
import json, sys
data = json.load(sys.stdin)
print(f\"p99: {data['golden_signals']['latency']['p99']} ms\")
"
```

### Application: Per-Endpoint Error Rate

```bash
curl -s http://localhost:8000/ops/metrics | python -c "
import json, sys
data = json.load(sys.stdin)
for ep, red in data['by_endpoint'].items():
    if red['errors'] > 0:
        print(f\"{ep}: error_rate={red['errors']:.6f}, rate={red['rate']}/s\")
"
```

### OTEL Collector: Debug / Verify Export

```bash
# Check collector is receiving data (debug exporter logs to stdout)
docker compose logs otel-collector --tail 20

# Verify gRPC connectivity from the service container
docker compose exec tvevents-api python -c "
import grpc
channel = grpc.insecure_channel('otel-collector:4317')
print('channel state:', channel._channel.check_connectivity_state(True))
"
```
