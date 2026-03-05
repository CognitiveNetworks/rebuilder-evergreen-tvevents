# ADR 001: Use Python 3.12 and FastAPI

## Status
Accepted

## Context
The legacy evergreen-tvevents service runs on Python 3.10 with Flask and gevent for async support. The API Surface Health audit rated the existing API as **Poor**: there is no OpenAPI specification, no typed responses, and Flask requires monkey-patching via gevent to handle concurrent requests. This limits developer productivity, makes contract testing impossible, and increases the risk of runtime type errors reaching production.

Python 3.12 brings significant performance improvements (specializing adaptive interpreter, per-interpreter GIL groundwork) and is the current stable release with long-term support.

## Decision
Use **Python 3.12** with **FastAPI** as the backend framework for the rebuilt service.

## Alternatives Considered
- **Keep Flask** — Rejected. Flask does not generate OpenAPI specs automatically, requires gevent monkey-patching for async, and lacks built-in request/response validation. Continuing with Flask would perpetuate the Poor API Surface Health rating.
- **Django REST Framework** — Rejected. Django is a full-stack web framework with ORM, admin panel, and middleware that are unnecessary for a focused API service. The overhead is not justified for a service with a small number of endpoints.
- **Starlette** — Rejected. FastAPI is built on top of Starlette, adding Pydantic-based request/response validation, automatic OpenAPI generation, and dependency injection. Using Starlette directly would require reimplementing these features manually.

## Consequences
- **Native async/await** — FastAPI runs on ASGI (uvicorn), eliminating the need for gevent monkey-patching. I/O-bound operations (database queries, Kafka publishing, Redis lookups) can run concurrently without thread hacks.
- **Auto-generated OpenAPI** — Every endpoint automatically produces an OpenAPI 3.1 spec at `/docs` and `/openapi.json`. Contract testing and client generation become possible immediately.
- **Pydantic validation** — Request bodies, query parameters, and response models are validated at the framework level. Type mismatches are caught before handler code executes.
- **Trade-off: team familiarity** — Team members experienced with Flask will need to learn FastAPI patterns (dependency injection, async handlers, Pydantic models). FastAPI's documentation is extensive, and the migration is straightforward for developers already comfortable with Python type hints.
