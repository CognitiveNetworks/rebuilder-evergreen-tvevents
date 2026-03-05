"""SRE diagnostic endpoints — ``GET /ops/*``.

Every endpoint returns real data from live service state, not placeholders.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Request

from tvevents import __version__
from tvevents.api.models import (
    ConfigResponse,
    DependenciesResponse,
    DependencyStatus,
    ErrorEntry,
    ErrorsResponse,
    MetricsResponse,
    StatusResponse,
)
from tvevents.middleware.metrics import MetricsCollector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["ops-diagnostics"])

# ── Shared error buffer ──────────────────────────────────────────────────
# Circular buffer storing the last 100 errors.  Populated by the exception
# handlers in main.py.
MAX_ERROR_BUFFER = 100
error_buffer: deque[ErrorEntry] = deque(maxlen=MAX_ERROR_BUFFER)

# Secrets that must be redacted in /ops/config output
_REDACT_FIELDS = frozenset(
    {
        "t1_salt",
        "rds_pass",
        "redis_password",
        "kafka_sasl_password",
        "kafka_sasl_username",
    }
)


def record_error(entry: ErrorEntry) -> None:
    """Append an error to the shared circular buffer."""
    error_buffer.append(entry)


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Service status with uptime and environment",
)
async def ops_status(request: Request) -> StatusResponse:
    """Return service identity, version, environment, uptime, and drain state."""
    state = request.app.state
    uptime = time.monotonic() - getattr(state, "start_time", time.monotonic())
    return StatusResponse(
        service=state.settings.service_name,
        version=__version__,
        environment=state.settings.zoo,
        uptime_seconds=round(uptime, 2),
        drain_mode=getattr(state, "drain_mode", False),
    )


@router.get(
    "/health",
    summary="Detailed dependency health (Kafka, RDS, Redis, OTEL)",
)
async def ops_health(request: Request) -> dict[str, Any]:
    """Detailed per-dependency health (mirrors ``/health`` but under ``/ops``)."""
    state = request.app.state
    checks: dict[str, dict[str, Any]] = {}

    for name, svc_attr in [("kafka", "kafka"), ("rds", "rds"), ("redis", "redis")]:
        svc = getattr(state, svc_attr, None)
        if svc is None:
            checks[name] = {"status": "not_configured"}
            continue
        try:
            if name == "redis":
                result = await svc.ping()
                healthy = bool(result)
            else:
                healthy = await svc.health_check()
            checks[name] = {"status": "healthy" if healthy else "unhealthy"}
        except Exception as exc:
            checks[name] = {"status": "unhealthy", "error": str(exc)}

    # OTEL — check if tracer provider is live
    try:
        from opentelemetry import trace as _trace  # noqa: PLC0415

        provider = _trace.get_tracer_provider()
        checks["otel"] = {"status": "healthy" if provider is not None else "unhealthy"}
    except Exception as exc:
        checks["otel"] = {"status": "unhealthy", "error": str(exc)}

    return {"checks": checks}


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Golden Signals + RED metrics from live traffic",
)
async def ops_metrics(request: Request) -> MetricsResponse:
    """Return computed metrics from the :class:`MetricsCollector`.

    Data comes from live request interception — this endpoint never
    returns placeholder zeros after the first request.
    """
    # Update saturation data from services before returning
    state = request.app.state
    collector = MetricsCollector()

    rds = getattr(state, "rds", None)
    if rds is not None and rds.pool_size > 0:
        utilisation = 1.0 - (rds.pool_free / max(rds.pool_size, 1))
        collector.update_saturation("rds_pool", round(utilisation, 3))

    return collector.get_metrics()


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Sanitised runtime configuration (secrets redacted)",
)
async def ops_config(request: Request) -> ConfigResponse:
    """Return the current settings with sensitive fields masked."""
    settings = request.app.state.settings
    raw = settings.model_dump()
    sanitised = {k: "***REDACTED***" if k in _REDACT_FIELDS else v for k, v in raw.items()}
    return ConfigResponse(config=sanitised)


@router.get(
    "/dependencies",
    response_model=DependenciesResponse,
    summary="List all dependencies with status",
)
async def ops_dependencies(request: Request) -> DependenciesResponse:
    """Enumerate every external dependency and its current status."""
    state = request.app.state
    deps: list[DependencyStatus] = []

    dep_specs: list[tuple[str, str, str]] = [
        ("kafka", "message_queue", "kafka"),
        ("rds", "database", "rds"),
        ("redis", "cache", "redis"),
    ]

    for name, dep_type, attr in dep_specs:
        svc = getattr(state, attr, None)
        if svc is None:
            deps.append(DependencyStatus(name=name, type=dep_type, status="not_configured"))
            continue
        start = time.monotonic()
        try:
            if name == "redis":
                result = await svc.ping()
                healthy = bool(result)
            else:
                healthy = await svc.health_check()
            latency = round((time.monotonic() - start) * 1000, 2)
            deps.append(
                DependencyStatus(
                    name=name,
                    type=dep_type,
                    status="healthy" if healthy else "unhealthy",
                    latency_ms=latency,
                )
            )
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            deps.append(
                DependencyStatus(
                    name=name,
                    type=dep_type,
                    status="unhealthy",
                    latency_ms=latency,
                    error=str(exc),
                )
            )

    return DependenciesResponse(dependencies=deps)


@router.get(
    "/errors",
    response_model=ErrorsResponse,
    summary="Recent errors (last 100)",
)
async def ops_errors() -> ErrorsResponse:
    """Return the circular buffer of recent errors."""
    entries = list(error_buffer)
    return ErrorsResponse(errors=entries, total=len(entries))
