"""SRE remediation endpoints — ``POST/PUT /ops/*``.

All endpoints log the caller IP, action name, and parameters for audit
purposes before performing any state change.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from tvevents.api.models import (
    CacheFlushResponse,
    CircuitsResponse,
    CircuitState,
    DrainResponse,
    LogLevelResponse,
    ScaleResponse,
)
from tvevents.middleware.metrics import MetricsCollector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["ops-remediation"])


# ── Request bodies ───────────────────────────────────────────────────────


class DrainRequest(BaseModel):
    """Body for ``POST /ops/drain``."""

    enabled: bool = Field(..., description="True to enable drain mode, False to disable")


class CircuitRequest(BaseModel):
    """Body for ``POST /ops/circuits``."""

    name: str = Field(..., description="Dependency name (kafka, rds, redis)")
    state: str = Field(..., description="Desired state: open, closed, half-open")


class LogLevelRequest(BaseModel):
    """Body for ``PUT /ops/loglevel``."""

    level: str = Field(
        ..., description="Desired log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _audit_log(request: Request, action: str, params: dict[str, Any]) -> None:
    """Emit a structured audit log entry for every remediation action."""
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "REMEDIATION action=%s caller=%s params=%s",
        action,
        client_ip,
        params,
    )


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post(
    "/drain",
    response_model=DrainResponse,
    summary="Enable or disable drain mode",
)
async def ops_drain(body: DrainRequest, request: Request) -> DrainResponse:
    """Toggle drain mode.

    When enabled, the ``/health`` endpoint returns 503, signalling the
    load balancer to stop sending traffic.  New requests to ``/v1/events``
    will also receive 503.
    """
    _audit_log(request, "drain", {"enabled": body.enabled})
    request.app.state.drain_mode = body.enabled
    state_label = "enabled" if body.enabled else "disabled"
    return DrainResponse(
        drain_mode=body.enabled,
        message=f"Drain mode {state_label}",
    )


@router.post(
    "/cache/flush",
    response_model=CacheFlushResponse,
    summary="Flush the Redis blacklist cache",
)
async def ops_cache_flush(request: Request) -> CacheFlushResponse:
    """Delete the Redis blacklist key to force a re-fetch from RDS."""
    _audit_log(request, "cache_flush", {})
    cache = getattr(request.app.state, "cache", None)
    if cache is None:
        return CacheFlushResponse(flushed=False, message="Cache service not available")
    try:
        await cache.flush_cache()
        return CacheFlushResponse(flushed=True, message="Blacklist cache flushed successfully")
    except Exception as exc:
        logger.error("Cache flush failed: %s", exc)
        return CacheFlushResponse(flushed=False, message=f"Flush failed: {exc}")


@router.post(
    "/circuits",
    response_model=CircuitsResponse,
    summary="Open or close circuit breakers",
)
async def ops_circuits(body: CircuitRequest, request: Request) -> CircuitsResponse:
    """Manually control circuit-breaker state for a named dependency.

    Circuit breaker state is stored in ``app.state.circuits``.  When a
    circuit is ``open``, the corresponding service client skips real calls
    and returns a fast-fail response.
    """
    _audit_log(request, "circuits", {"name": body.name, "state": body.state})

    circuits: dict[str, str] = getattr(request.app.state, "circuits", {})
    circuits[body.name] = body.state
    request.app.state.circuits = circuits

    circuit_list = [CircuitState(name=k, state=v) for k, v in circuits.items()]
    return CircuitsResponse(
        circuits=circuit_list,
        message=f"Circuit '{body.name}' set to '{body.state}'",
    )


@router.put(
    "/loglevel",
    response_model=LogLevelResponse,
    summary="Change log level at runtime",
)
async def ops_loglevel(body: LogLevelRequest, request: Request) -> LogLevelResponse:
    """Dynamically adjust the root logger level without a restart."""
    _audit_log(request, "loglevel", {"level": body.level})

    root_logger = logging.getLogger()
    previous = logging.getLevelName(root_logger.level)
    new_level = body.level.upper()

    numeric = logging.getLevelNamesMapping().get(new_level)
    if numeric is None:
        return LogLevelResponse(
            previous=previous,
            current=previous,
            message=f"Invalid log level: {body.level}",
        )

    root_logger.setLevel(numeric)
    # Also update the tvevents logger hierarchy
    logging.getLogger("tvevents").setLevel(numeric)

    return LogLevelResponse(
        previous=previous,
        current=new_level,
        message=f"Log level changed to {new_level}",
    )


@router.post(
    "/scale",
    response_model=ScaleResponse,
    summary="Advisory scaling recommendation",
)
async def ops_scale(request: Request) -> ScaleResponse:
    """Compute a recommended replica count based on current throughput.

    This is advisory only — it does not trigger actual scaling.  Useful
    for SRE dashboards and autoscaler tuning.
    """
    _audit_log(request, "scale", {})

    collector = MetricsCollector()
    metrics = collector.get_metrics()

    current_rps = metrics.golden_signals.traffic_per_sec
    # Heuristic: 1 pod per 1000 RPS, minimum 2
    recommended = max(2, int(current_rps / 1000) + 1)

    return ScaleResponse(
        recommended_replicas=recommended,
        current_rps=current_rps,
        message="Advisory: scaling recommendation based on current traffic",
    )
