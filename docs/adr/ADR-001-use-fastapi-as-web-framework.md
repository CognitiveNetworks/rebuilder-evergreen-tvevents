# ADR 001: Use FastAPI as Web Framework

## Status

Accepted

## Context

The legacy tvevents-k8s service uses Flask 3.1.1 with Gunicorn + gevent workers. The legacy assessment identified several gaps: no OpenAPI spec, no typed request/response models, no Pydantic validation, and no auto-generated API documentation. The organization is standardizing on FastAPI for new Python services. The user explicitly requires FastAPI as the web framework for this rebuild.

## Decision

Replace Flask with FastAPI as the web framework. Use Pydantic v2 models for all request/response types. Auto-generate the OpenAPI spec via FastAPI's built-in support. Run on Uvicorn instead of Gunicorn + gevent.

## Alternatives Considered

- **Keep Flask** — Rejected. Flask does not provide auto-generated OpenAPI specs, typed response models, or built-in Pydantic integration. The user explicitly overrides Flask in favor of FastAPI.
- **Starlette (bare)** — Rejected. FastAPI is built on Starlette and adds typed models, dependency injection, and OpenAPI generation. No reason to use the lower-level framework directly.

## Consequences

- **Positive:** Auto-generated OpenAPI spec with Swagger UI, typed Pydantic models for all endpoints, better error handling with structured validation errors, async support for future use.
- **Negative:** Team must learn FastAPI patterns. gevent is not used with Uvicorn — verify no gevent-specific patterns exist in business logic. Pydantic strict validation may reject edge-case payloads that Flask accepted silently.
- **Mitigation:** Test with production-representative payloads. Configure `model_config = ConfigDict(extra="allow")` where backward compatibility requires it.
