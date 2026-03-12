# ADR 001: Framework Selection — FastAPI over Flask

## Status

Accepted

## Context

The legacy evergreen-tvevents service runs on Python 3.10 with Flask 3.1.1, served by Gunicorn with gevent workers (3 workers, 500 connections each). This configuration handles the high-throughput TV telemetry ingestion workload through cooperative concurrency but offers no native async support. Flask provides no built-in request validation, no automatic OpenAPI documentation generation, and no dependency injection framework.

The service's single primary endpoint receives POST requests from SmartCast devices at extremely high volume. Every request must be validated (security hash verification), classified (event type routing), optionally obfuscated (channel masking), and delivered to analytics pipelines. The processing pipeline is I/O-heavy — involving cache lookups, potential database queries, and multi-stream delivery — making it a strong candidate for async execution.

The rebuilder-evergreen-template-repo-python project establishes the canonical service template for all rebuilt services. That template uses FastAPI with uvicorn, Pydantic models, and auto-generated OpenAPI documentation. Aligning with this template is a non-negotiable project constraint to ensure consistency across the rebuilt service fleet.

The modernization assessment identified the Flask-to-FastAPI migration as a Go decision, noting that FastAPI's native async support, Pydantic integration, and OpenAPI auto-generation directly address three separate modernization opportunities in a single framework change.

## Decision

Adopt FastAPI ≥ 0.115.0 with uvicorn ≥ 0.34.0 as the web framework and ASGI server, replacing Flask 3.1.1 and Gunicorn+gevent.

In Phase 1, internal I/O-bound operations (database queries, delivery calls) will use `asyncio.to_thread` wrappers around synchronous implementations. This provides the async endpoint surface immediately while deferring the complexity of fully async drivers to later phases. Pydantic models will define all request and response schemas, and OpenAPI documentation will be auto-generated from those models.

## Alternatives Considered

**Keep Flask 3.1.1 with Gunicorn+gevent.** This would minimize migration effort but perpetuates the lack of native async support, automatic API documentation, and Pydantic validation. Flask does not match the template-repo-python pattern, which would make this service an outlier in the rebuilt fleet. The gevent monkey-patching model also introduces subtle compatibility risks with modern async libraries. Rejected.

**Django REST Framework.** Django is a full-featured web framework with an ORM, admin interface, and middleware ecosystem. For a single-endpoint ingestion service that performs no CRUD operations and requires no admin UI, Django's footprint is excessive. It does not match the template pattern, and its ORM would go entirely unused. Rejected.

**Starlette (bare ASGI framework).** FastAPI is built on Starlette, so using Starlette directly eliminates the FastAPI abstraction layer. However, this sacrifices automatic Pydantic validation, dependency injection, and OpenAPI generation — all of which would need to be reimplemented manually. The marginal performance gain does not justify the lost developer productivity. Rejected.

## Consequences

**Positive:**
- Auto-generated OpenAPI documentation from Pydantic models eliminates manual API spec maintenance.
- Pydantic request validation catches malformed telemetry payloads at the framework level before business logic executes.
- Native async/await support enables future migration to fully async I/O without changing the endpoint signatures.
- Exact alignment with rebuilder-evergreen-template-repo-python ensures fleet consistency and shared tooling.
- Dependency injection simplifies testing by allowing mock injection of database, cache, and delivery dependencies.

**Negative:**
- Team requires FastAPI/Pydantic familiarity; training or ramp-up time is expected.
- Phase 1 uses `to_thread` wrappers around synchronous internals, which adds a thin abstraction layer without immediate async performance gains. The benefit is realized when async drivers are adopted in later phases.
- Subtle behavioral differences between Flask and FastAPI (middleware ordering, error handling, request lifecycle) require careful validation during migration.
