# ADR 008: OTEL Collector for Observability

## Status
Accepted

## Context
The legacy service has observability implemented through embedded vendor SDKs: `pygerduty` for PagerDuty alerting and direct New Relic integration for metrics and tracing. This approach couples the application code to specific monitoring vendors, making it difficult to switch backends, creates inconsistent instrumentation patterns, and mixes alerting logic with business logic.

## Decision
The application emits standardized **OpenTelemetry** signals (traces, metrics, logs) using the OpenTelemetry Python SDK. An **OTEL Collector sidecar** runs alongside the application in each pod, receiving telemetry via OTLP and exporting to observability backends. No vendor-specific SDKs are embedded in the application.

## Alternatives Considered
- **Keep New Relic direct integration** — Rejected. Embedding the New Relic SDK in the application creates vendor lock-in. Switching observability backends would require application code changes, testing, and redeployment. The application should not know or care which backend consumes its telemetry.
- **Datadog agent** — Rejected. Same vendor lock-in problem as New Relic. The Datadog agent collects telemetry well, but coupling the application to Datadog's SDK and conventions limits future flexibility.
- **Prometheus only** — Rejected. Prometheus handles metrics well but does not natively support distributed traces or structured logs. OpenTelemetry provides a unified framework for all three signal types, and the OTEL Collector can export to Prometheus as one of many backends.

## Consequences
- **Vendor-neutral observability** — The application emits standard OTLP signals. The observability backend (New Relic, Datadog, Grafana Cloud, self-hosted) is configured in the OTEL Collector, not in the application. Backend migration requires only Collector configuration changes.
- **Unified telemetry** — Traces, metrics, and logs use consistent context propagation (trace IDs, span IDs). Correlating a slow request to its database query to its log output becomes straightforward.
- **No vendor SDKs in application code** — Application dependencies are limited to `opentelemetry-api` and `opentelemetry-sdk`. Vendor-specific exporters live in the Collector configuration.
- **Trade-off: sidecar overhead** — The OTEL Collector runs as a sidecar container in each pod, consuming additional CPU and memory. Resource requests/limits must be configured appropriately to avoid impacting the application.
