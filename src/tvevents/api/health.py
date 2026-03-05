"""Health-check endpoint — ``GET /health``.

Checks Kafka, RDS, and Redis connectivity.  Returns 200 when all critical
dependencies are healthy, 503 otherwise.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request, Response

from tvevents import __version__
from tvevents.api.models import HealthCheckDetail, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def _check_dependency(
    name: str,
    check_fn: Any,
) -> HealthCheckDetail:
    """Run a single health check, capturing latency and errors."""
    start = time.monotonic()
    try:
        healthy: bool = await check_fn()
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return HealthCheckDetail(
            status="healthy" if healthy else "unhealthy",
            latency_ms=elapsed_ms,
            error=None if healthy else "check returned False",
        )
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return HealthCheckDetail(
            status="unhealthy",
            latency_ms=elapsed_ms,
            error=str(exc),
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
    summary="Dependency health check",
)
async def health(request: Request, response: Response) -> HealthResponse:
    """Check Kafka, RDS, and Redis connectivity.

    Returns **200** when all dependencies are healthy, **503** if any
    critical dependency is unreachable.
    """
    state = request.app.state
    drain_mode: bool = getattr(state, "drain_mode", False)

    if drain_mode:
        response.status_code = 503
        return HealthResponse(
            status="draining",
            checks={},
            version=__version__,
        )

    checks: dict[str, HealthCheckDetail] = {}

    # Kafka
    kafka = getattr(state, "kafka", None)
    if kafka is not None:
        checks["kafka"] = await _check_dependency("kafka", kafka.health_check)

    # RDS
    rds = getattr(state, "rds", None)
    if rds is not None:
        checks["rds"] = await _check_dependency("rds", rds.health_check)

    # Redis
    redis_client = getattr(state, "redis", None)
    if redis_client is not None:

        async def _redis_ping() -> bool:
            result = await redis_client.ping()
            return bool(result)

        checks["redis"] = await _check_dependency("redis", _redis_ping)

    all_healthy = all(c.status == "healthy" for c in checks.values())
    overall = "healthy" if all_healthy else "unhealthy"

    if not all_healthy:
        response.status_code = 503

    return HealthResponse(
        status=overall,
        checks=checks,
        version=__version__,
    )
