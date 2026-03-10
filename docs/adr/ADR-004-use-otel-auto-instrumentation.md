# ADR 004: Use OTEL Auto-Instrumentation

## Status

Accepted

## Context

The legacy tvevents-k8s service has manual OTEL instrumentation with explicit `Psycopg2Instrumentor().instrument()`, `FlaskInstrumentor().instrument_app(app)`, and five other instrumentor calls in `app/__init__.py`. This is verbose and requires code changes when adding new instrumented libraries. The `evergreen-template-repo-python` uses `opentelemetry-bootstrap` and `opentelemetry-instrument` for auto-instrumentation. The user explicitly requires OTEL auto-instrumentation.

## Decision

Use OTEL auto-instrumentation via `opentelemetry-instrument` CLI wrapper in entrypoint.sh. Run `opentelemetry-bootstrap` in the Dockerfile to install required instrumentation packages automatically. Retain manual spans only for business-specific tracing (event type processing, obfuscation decisions, delivery). Configure OTEL entirely via environment variables.

## Alternatives Considered

- **Keep manual instrumentation** — Rejected. Verbose, requires code changes for each new library. Does not follow template repo pattern. User explicitly requires auto-instrumentation.
- **No OTEL (vendor-specific APM)** — Rejected. OTEL is the organization's standard for telemetry. New Relic receives data via OTLP exporters, not a vendor-specific agent.

## Consequences

- **Positive:** Reduces boilerplate code. New libraries are automatically instrumented without code changes. Follows template repo pattern. Configuration via environment variables is easier to manage across environments.
- **Negative:** Auto-instrumentation may add overhead from instrumenting libraries that don't need it. Less control over span attributes compared to manual instrumentation. Must verify FastAPI auto-instrumentation produces equivalent trace data.
- **Mitigation:** Use `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` environment variable to disable unnecessary instrumentors. Retain manual spans for business-critical tracing paths.
