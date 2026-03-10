# ADR 007: Follow evergreen-template-repo-python Operational Patterns

## Status

Accepted

## Context

The legacy tvevents-k8s service has operational files (Dockerfile, entrypoint.sh, environment-check.sh, Helm charts, dependency management) that do not follow the `evergreen-template-repo-python` patterns. This creates inconsistency across services and complicates operational procedures. The user explicitly requires following the template repo patterns for all operational files. Key patterns include: pip-compile workflow (`pyproject.toml` → `requirements.txt` via `scripts/lock.sh`), Dockerfile structure (pinned base image, `opentelemetry-bootstrap`, non-root user), entrypoint.sh (environment-check, OTEL conditional, ASGI server launch), and environment-check.sh (grouped variable validation with TEST_CONTAINER mode).

## Decision

Align all operational files with the `evergreen-template-repo-python` patterns:
- `Dockerfile` — follow template structure with pip install from compiled `requirements.txt`, `opentelemetry-bootstrap`, non-root user
- `entrypoint.sh` — source environment-check.sh, configure AWS, conditional OTEL, initialize blacklist cache, launch Uvicorn
- `environment-check.sh` — grouped variable validation (RDS, Kafka, app, OTEL), TEST_CONTAINER mode
- `scripts/lock.sh` — pip-compile workflow generating `requirements.txt` with hashes
- `charts/` — Helm chart templates following template repo structure

## Alternatives Considered

- **Keep legacy operational files** — Rejected. Creates inconsistency across services. Legacy Dockerfile includes cnlib `setup.py install` which is being eliminated. Legacy environment-check.sh references Firehose variables which are being replaced.
- **Custom operational patterns** — Rejected. The template repo exists specifically to standardize operational files. Custom patterns defeat the purpose of the template.

## Consequences

- **Positive:** Consistent operational files across all Python services. Standardized dependency management via pip-compile. Standardized container build. Standardized environment validation. Operations team can apply the same procedures to all services.
- **Negative:** Helm chart migration requires values.yaml restructuring. Some template patterns may not cover tvevents-specific configurations (e.g., blacklist cache initialization in entrypoint.sh).
- **Mitigation:** Extend template patterns where needed (e.g., add cache initialization step to entrypoint.sh) without breaking the standard structure.
