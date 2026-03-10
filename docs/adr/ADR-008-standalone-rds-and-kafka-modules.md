# ADR 008: Create Standalone RDS and Kafka Python Modules

## Status

Accepted

## Context

The legacy tvevents-k8s service embeds database access directly in `app/dbhelper.py` and event delivery in `app/utils.py` (via cnlib.firehose). These integrations lack connection pooling, standardized retry logic, and reusable interfaces. The user explicitly requires standalone RDS and Kafka Python modules outside the main repo for reusability across services.

## Decision

Create two standalone Python packages:
- `output/rebuilder-rds-module/` — `RdsClient` with connection pooling, retry with exponential backoff and jitter, OTEL instrumentation, health check, and proper connection lifecycle management.
- `output/rebuilder-kafka-module/` — `KafkaProducerClient` with confluent-kafka, SASL/SCRAM authentication, OTEL instrumentation, produce/flush/health check, and proper cleanup.

Both modules are self-contained packages with `pyproject.toml`, `src/` layout, tests, `.env.example`, and README.

## Alternatives Considered

- **Embed in the service** — Rejected. User explicitly requires standalone modules outside the repo. Embedded code is not reusable across services.
- **Publish to private PyPI** — Deferred. Modules are currently vendored in `output/`. Publishing to a private registry is a future step once the modules are validated in production.
- **Use existing shared libraries (cnlib)** — Rejected. cnlib is being eliminated. The standalone modules replace its Firehose and database functionality with modern, OTEL-instrumented implementations.

## Consequences

- **Positive:** Reusable across services. Each module has its own tests and can be versioned independently. Clean separation of concerns — the service imports a client, not raw SDK calls. Connection pooling and retry logic are standardized.
- **Negative:** Two additional packages to maintain. Module versioning and distribution (vendored vs. published) adds complexity. Changes to the module require updating the consuming service.
- **Mitigation:** Modules are small and focused (~150 lines each). Vendored in `output/` for now; publish to private registry when adoption grows.
