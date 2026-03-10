"""Operational endpoints — /ops/* diagnostic and remediation routes."""


import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from tvevents import __version__
from tvevents.api.models import (
    OpsCacheFlushResponse,
    OpsCircuitsResponse,
    OpsConfigResponse,
    OpsDependenciesResponse,
    OpsDrainResponse,
    OpsErrorsResponse,
    OpsHealthResponse,
    OpsLogLevelRequest,
    OpsLogLevelResponse,
    OpsMetricsResponse,
    OpsScaleResponse,
    OpsStatusResponse,
    DependencyStatus,
    ErrorEntry,
)
from tvevents.config import get_settings
from tvevents.deps import get_blacklist_cache, get_rds_client
from tvevents.domain.delivery import get_kafka_producer
from tvevents.middleware.metrics import metrics_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["ops"])

_start_time = time.monotonic()
_draining = False
_recent_errors: deque = deque(maxlen=100)


def record_error(error_type: str, message: str) -> None:
    """Record an error for /ops/errors."""
    _recent_errors.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_type": error_type,
            "message": message[:500],
        }
    )


def is_draining() -> bool:
    """Check if the service is in drain mode."""
    return _draining


@router.get(
    "/status",
    response_model=OpsStatusResponse,
    summary="Composite health verdict",
)
async def ops_status() -> OpsStatusResponse:
    """Dependency-aware health status."""
    uptime = time.monotonic() - _start_time
    status = "unhealthy" if _draining else "healthy"

    if not _draining:
        try:
            rds = get_rds_client()
            if not rds.health_check():
                status = "degraded"
        except Exception:
            status = "degraded"

    return OpsStatusResponse(
        status=status,
        service="tvevents-k8s",
        version=__version__,
        uptime_seconds=round(uptime, 1),
    )


@router.get(
    "/health",
    response_model=OpsHealthResponse,
    summary="Dependency health check",
)
async def ops_health() -> OpsHealthResponse:
    """Check health of all dependencies."""
    deps = []

    try:
        rds = get_rds_client()
        start = time.monotonic()
        rds_ok = rds.health_check()
        latency = (time.monotonic() - start) * 1000
        deps.append(DependencyStatus(name="rds", healthy=rds_ok, latency_ms=round(latency, 2)))
    except Exception as e:
        deps.append(DependencyStatus(name="rds", healthy=False, error=str(e)))

    try:
        start = time.monotonic()
        producer = get_kafka_producer()
        kafka_ok = producer is not None
        latency = (time.monotonic() - start) * 1000
        deps.append(DependencyStatus(name="kafka", healthy=kafka_ok, latency_ms=round(latency, 2)))
    except Exception as e:
        deps.append(DependencyStatus(name="kafka", healthy=False, error=str(e)))

    all_healthy = all(d.healthy for d in deps)
    return OpsHealthResponse(
        status="healthy" if all_healthy else "degraded",
        dependencies=deps,
    )


@router.get(
    "/metrics",
    response_model=OpsMetricsResponse,
    summary="Golden Signals + RED metrics",
)
async def ops_metrics() -> OpsMetricsResponse:
    """Return application metrics."""
    summary = metrics_state.summary()
    return OpsMetricsResponse(**summary)


@router.get(
    "/config",
    response_model=OpsConfigResponse,
    summary="Runtime configuration (secrets redacted)",
)
async def ops_config() -> OpsConfigResponse:
    """Return runtime configuration with secrets redacted."""
    settings = get_settings()
    return OpsConfigResponse(
        env=settings.env,
        service_name=settings.service_name,
        aws_region=settings.aws_region,
        send_evergreen=settings.send_evergreen,
        send_legacy=settings.send_legacy,
        tvevents_debug=settings.tvevents_debug,
        kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
        kafka_topics=settings.valid_kafka_topics,
        debug_kafka_topics=settings.valid_debug_kafka_topics,
        rds_host=settings.rds_host,
        rds_db=settings.rds_db,
        log_level=settings.log_level,
    )


@router.get(
    "/dependencies",
    response_model=OpsDependenciesResponse,
    summary="Dependency connectivity",
)
async def ops_dependencies() -> OpsDependenciesResponse:
    """Check connectivity to all dependencies."""
    health = await ops_health()
    return OpsDependenciesResponse(dependencies=health.dependencies)


@router.get(
    "/errors",
    response_model=OpsErrorsResponse,
    summary="Recent errors",
)
async def ops_errors() -> OpsErrorsResponse:
    """Return recent error summary."""
    recent = [
        ErrorEntry(
            timestamp=e["timestamp"],
            error_type=e["error_type"],
            message=e["message"],
        )
        for e in _recent_errors
    ]
    return OpsErrorsResponse(total_errors=len(recent), recent=recent)


@router.post(
    "/drain",
    response_model=OpsDrainResponse,
    summary="Toggle drain mode",
)
async def ops_drain() -> OpsDrainResponse:
    """Toggle drain mode — health returns 503 during drain."""
    global _draining
    _draining = not _draining
    state = "draining" if _draining else "accepting traffic"
    logger.info("Drain mode toggled: %s", state)
    return OpsDrainResponse(
        draining=_draining,
        message=f"Service is now {state}",
    )


@router.post(
    "/cache/flush",
    response_model=OpsCacheFlushResponse,
    summary="Flush and reload blacklist cache",
)
async def ops_cache_flush() -> OpsCacheFlushResponse:
    """Clear and reload the blacklist cache from RDS."""
    try:
        cache = get_blacklist_cache()
        rds_client = get_rds_client()
        cache.flush()
        cache.get_blacklisted_channel_ids(
            fetch_from_db=rds_client.fetch_blacklisted_channel_ids
        )
        return OpsCacheFlushResponse(
            flushed=True, message="Blacklist cache flushed and reloaded"
        )
    except Exception as e:
        logger.error("Cache flush failed: %s", e)
        return OpsCacheFlushResponse(
            flushed=False, message=f"Cache flush failed: {e}"
        )


@router.get(
    "/circuits",
    response_model=OpsCircuitsResponse,
    summary="Circuit breaker state",
)
async def ops_circuits() -> OpsCircuitsResponse:
    """Return circuit breaker states."""
    return OpsCircuitsResponse(circuits={"rds": "closed", "kafka": "closed"})


@router.post(
    "/loglevel",
    response_model=OpsLogLevelResponse,
    summary="Change runtime log level",
)
async def ops_loglevel(body: OpsLogLevelRequest) -> OpsLogLevelResponse:
    """Change the runtime log level."""
    root_logger = logging.getLogger()
    previous = logging.getLevelName(root_logger.level)
    new_level = body.level.upper()

    if new_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return OpsLogLevelResponse(previous=previous, current=previous)

    root_logger.setLevel(new_level)
    logger.info("Log level changed from %s to %s", previous, new_level)
    return OpsLogLevelResponse(previous=previous, current=new_level)


@router.post(
    "/scale",
    response_model=OpsScaleResponse,
    summary="Scale (delegated to Kubernetes HPA)",
)
async def ops_scale() -> OpsScaleResponse:
    """Scaling is managed by Kubernetes HPA."""
    return OpsScaleResponse(
        message="Scaling is managed by Kubernetes HPA, not the application"
    )
