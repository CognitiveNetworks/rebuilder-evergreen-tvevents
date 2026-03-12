# ADR 005: Observability Approach — OTEL Auto-Instrumentation over Manual Setup

## Status

Accepted

## Context

The legacy evergreen-tvevents service implements OpenTelemetry manually with approximately 48 lines of boilerplate code. This setup explicitly configures `TracerProvider`, `MeterProvider`, and `LoggerProvider`, registers OTLP exporters for each signal, and individually instruments six libraries (Flask, psycopg2, urllib3, requests, logging, and jinja2). The manual setup is spread across the service initialization code and must be maintained whenever OTEL dependencies are updated or new libraries are added.

This manual approach is error-prone: missing an instrumentor means missing telemetry for that library, version mismatches between OTEL packages cause subtle failures, and the boilerplate must be replicated (with modifications) in every service. The legacy assessment identified this as a significant modernization opportunity — the 48 lines of boilerplate can be replaced by auto-instrumentation that discovers and activates instrumentors automatically.

The rebuilder-evergreen-template-repo-python establishes the canonical observability pattern: OTEL auto-instrumentation via `opentelemetry-bootstrap`, `FastAPIInstrumentor`, and environment-variable-driven configuration. The template eliminates manual provider setup entirely, relying on the OTEL SDK's automatic configuration from environment variables (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, etc.).

## Decision

Adopt OTEL auto-instrumentation, replacing all manual provider setup and per-library instrumentation. The implementation uses:

- `FastAPIInstrumentor` for automatic HTTP request/response tracing
- `Psycopg2Instrumentor` for automatic database query tracing
- `URLLib3Instrumentor` for automatic outbound HTTP call tracing
- Environment-variable-driven OTEL configuration (no code-level provider setup)
- `opentelemetry-bootstrap` for instrumentor discovery and installation

Golden Signals (latency, traffic, errors, saturation) will be auto-captured through the framework and library instrumentors. Custom metrics will be added only where auto-instrumentation does not cover service-specific needs (e.g., events-per-type counters, cache hit/miss ratios, delivery success/failure rates per topic).

## Alternatives Considered

**Keep manual OTEL setup.** This preserves the existing 48-line boilerplate with full control over every provider, exporter, and instrumentor. However, it is maintenance-heavy, error-prone (missed instrumentors, version skew), and does not match the template pattern. Every service would carry its own variant of the boilerplate, making fleet-wide observability updates expensive. Rejected.

**Datadog agent with APM.** Datadog provides automatic instrumentation through its agent and ddtrace library. This creates vendor lock-in to Datadog's proprietary telemetry format and conflicts with the organization's OpenTelemetry standardization strategy. OTEL provides vendor-neutral telemetry that can be routed to any backend (Datadog, Grafana, Jaeger, etc.) via the OTEL Collector. Rejected.

**No instrumentation.** Operating a high-throughput production service without observability is unacceptable. The service handles TV telemetry from millions of SmartCast devices; without tracing, metrics, and structured logging, diagnosing latency issues, delivery failures, or capacity problems would require manual log analysis. Rejected.

## Consequences

**Positive:**
- Eliminates ~48 lines of manual OTEL boilerplate, reducing initialization code to near-zero.
- Template alignment ensures consistent observability patterns across the rebuilt service fleet.
- Auto-captured Golden Signals provide immediate production visibility without custom instrumentation code.
- New library instrumentors are discovered automatically by `opentelemetry-bootstrap`, reducing the risk of blind spots when dependencies change.
- Environment-variable-driven configuration enables per-environment tuning (sampling rate, exporter endpoint, service name) without code changes.

**Negative:**
- Less granular control over individual span attributes and metric dimensions compared to manual setup. Mitigated by adding custom metrics where auto-instrumentation falls short.
- Dependency on `opentelemetry-bootstrap` for instrumentor discovery. If a new library is added and no instrumentor exists, that library's calls will not be traced automatically.
- Auto-instrumentation may capture spans for internal framework operations that are not useful, potentially increasing telemetry volume. Span filtering can be configured via environment variables or OTEL Collector pipelines.
