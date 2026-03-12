"""API routes — POST /, GET /status, /health, /ops/* SRE endpoints."""

import json
import logging
import os
import time
from collections import deque
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace

from app import configure_logging, meter
from app.blacklist import blacklist_cache
from app.exceptions import TvEventsDefaultError
from app.output import push_changes_to_kafka
from app.validation import validate_request

LOGGER = configure_logging()

router = APIRouter()
tracer = trace.get_tracer(__name__)

VERSION = os.getenv("VERSION", "1.0.0")

SND_RQ_COUNTER = meter.create_counter(
    name="send_request_counter",
    description="Send Data for Processing",
)

# Track recent errors for /ops/errors
_recent_errors: list[dict] = []
_MAX_RECENT_ERRORS = 100

# --- Metrics collection for Golden Signals / RED ---
_drain_mode = False
_request_latencies: deque[float] = deque(maxlen=10000)
_request_count = 0
_error_count = 0
_start_time = time.monotonic()


def _record_error(error_type: str, message: str):
    """Record an error in the recent errors deque."""
    _recent_errors.append(
        {
            "type": error_type,
            "message": message[:200],
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    if len(_recent_errors) > _MAX_RECENT_ERRORS:
        _recent_errors.pop(0)


async def metrics_middleware(request: Request, call_next):
    """Middleware to collect Golden Signals / RED metrics for every request."""
    global _request_count, _error_count
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    _request_latencies.append(elapsed_ms)
    _request_count += 1
    if response.status_code >= 500:
        _error_count += 1
    return response


async def log_request_middleware(request: Request, call_next):
    """Middleware to capture incoming HTTP requests for logging."""
    if request.url.path in ["/status", "/health", "/ops/health"]:
        return await call_next(request)
    try:
        log_data = {
            "incoming_request": "access_log",
            "method": request.method,
            "path": request.url.path,
            "remote_client": request.client.host if request.client else None,
            "request_url": str(request.url),
            "headers": dict(request.headers),
        }
        LOGGER.info(json.dumps(log_data))
    except Exception as catchall_exception:
        LOGGER.error(
            "Exception in request logging middleware: %s",
            catchall_exception,
        )
        raise
    return await call_next(request)


@router.get("/status")
async def status():
    """Health check endpoint — returns bare 'OK' for backward compatibility."""
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(content="OK")


@router.post("/")
async def send_request(request: Request):
    """Route all TV event data for processing and Kafka delivery."""
    with tracer.start_as_current_span("send_request") as span:
        SND_RQ_COUNTER.add(1)
        url_params = dict(request.query_params)
        tvid = url_params.get("tvid", "")

        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(
                content={"error": "invalid_payload", "message": "Invalid JSON body"},
                status_code=400,
            )

        span.set_attributes(
            {
                "tvid": tvid,
                "event_type": url_params.get("event_type", "unknown"),
            }
        )

        LOGGER.info("JSON Payload: %s", payload)
        try:
            validate_request(url_params, payload)
            push_changes_to_kafka(payload)
        except TvEventsDefaultError as e:
            error_type = type(e).__name__
            _record_error(error_type, str(e))
            return JSONResponse(
                content={"error": error_type, "message": str(e)},
                status_code=e.status_code,
            )
        except Exception as catchall_exception:
            msg = f"Exception in send_request: tvid={tvid} msg={catchall_exception}"
            LOGGER.error(msg)
            _record_error("TvEventsCatchallError", msg)
            return JSONResponse(
                content={"error": "internal_error", "message": str(catchall_exception)},
                status_code=500,
            )

        return JSONResponse(content={"status": "ok"})


# --- /ops/* SRE Diagnostic Endpoints ---


@router.get("/ops/health")
async def ops_health():
    """Deep health check: Kafka, RDS, cache."""
    checks: dict = {}

    # Cache check
    checks["cache"] = {
        "status": "ok",
        "entries": blacklist_cache.entry_count,
        "age_seconds": round(blacklist_cache.age_seconds),
    }

    # RDS check
    rds_status = "ok"
    rds_latency = 0.0
    try:
        start = time.time()
        from rds_module import execute_query

        execute_query("SELECT 1;")
        rds_latency = round((time.time() - start) * 1000, 1)
    except Exception:
        rds_status = "error"
    checks["rds"] = {"status": rds_status, "latency_ms": rds_latency}

    # Kafka check
    kafka_status = "ok"
    kafka_latency = 0.0
    try:
        start = time.time()
        from kafka_module import health_check

        health_check()
        kafka_latency = round((time.time() - start) * 1000, 1)
    except Exception:
        kafka_status = "error"
    checks["kafka"] = {"status": kafka_status, "latency_ms": kafka_latency}

    overall = (
        "healthy" if all(c["status"] == "ok" for c in checks.values()) else "degraded"
    )
    return JSONResponse(content={"status": overall, "checks": checks})


@router.get("/ops/config")
async def ops_config():
    """Non-sensitive runtime configuration."""
    config = {
        "service_name": os.getenv("SERVICE_NAME", "evergreen-tvevents"),
        "version": VERSION,
        "zoo": os.getenv("ZOO", "unknown"),
        "send_evergreen": os.getenv("SEND_EVERGREEN", "false"),
        "send_legacy": os.getenv("SEND_LEGACY", "false"),
        "tvevents_debug": os.getenv("TVEVENTS_DEBUG", "false"),
        "kafka_topic_evergreen": os.getenv(
            "KAFKA_TOPIC_EVERGREEN", "evergreen-tvevents"
        ),
        "kafka_topic_legacy": os.getenv("KAFKA_TOPIC_LEGACY", "legacy-tvevents"),
        "cache_filepath": os.getenv(
            "BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH",
            "/tmp/.blacklisted_channel_ids_cache",  # noqa: S108
        ),
        "otel_enabled": os.getenv("OTEL_PYTHON_AUTO_INSTRUMENTATION_ENABLED", "false"),
        "log_level": os.getenv("LOG_LEVEL", "DEBUG"),
        "event_types_enabled": [
            "NATIVEAPP_TELEMETRY",
            "ACR_TUNER_DATA",
            "PLATFORM_TELEMETRY",
        ],
    }
    return JSONResponse(content=config)


@router.get("/ops/dependencies")
async def ops_dependencies():
    """Status of external dependencies with connectivity check."""
    deps: dict = {}

    # RDS
    try:
        start = time.time()
        from rds_module import execute_query

        execute_query("SELECT 1;")
        deps["rds"] = {
            "status": "ok",
            "latency_ms": round((time.time() - start) * 1000, 1),
        }
    except Exception as e:
        deps["rds"] = {"status": "error", "error": str(e)}

    # Kafka
    try:
        start = time.time()
        from kafka_module import health_check

        health_check()
        deps["kafka"] = {
            "status": "ok",
            "latency_ms": round((time.time() - start) * 1000, 1),
        }
    except Exception as e:
        deps["kafka"] = {"status": "error", "error": str(e)}

    # cnlib
    try:
        deps["cnlib"] = {"status": "ok"}
    except Exception as e:
        deps["cnlib"] = {"status": "error", "error": str(e)}

    return JSONResponse(content={"dependencies": deps})


@router.get("/ops/cache")
async def ops_cache():
    """Blacklist cache statistics and freshness."""
    return JSONResponse(
        content={
            "entry_count": blacklist_cache.entry_count,
            "cache_filepath": blacklist_cache.cache_filepath,
            "last_refresh": datetime.fromtimestamp(
                blacklist_cache.last_refresh_time, tz=UTC
            ).isoformat()
            if blacklist_cache.last_refresh_time > 0
            else None,
            "age_seconds": round(blacklist_cache.age_seconds),
        }
    )


@router.get("/ops/errors")
async def ops_errors():
    """Recent error summary by type."""
    error_counts: dict[str, int] = {}
    for err in _recent_errors:
        error_counts[err["type"]] = error_counts.get(err["type"], 0) + 1

    return JSONResponse(
        content={
            "total": len(_recent_errors),
            "by_type": error_counts,
            "recent": _recent_errors[-10:],
        }
    )


# --- /ops/* Safe Remediation Endpoints ---


@router.post("/ops/cache/refresh")
async def ops_cache_refresh():
    """Trigger blacklist cache refresh from RDS."""
    LOGGER.info("ops/cache/refresh triggered")
    success = blacklist_cache.refresh()
    if success:
        return JSONResponse(
            content={
                "status": "ok",
                "message": "Cache refreshed",
                "entries": blacklist_cache.entry_count,
            }
        )
    return JSONResponse(
        content={"status": "error", "message": "Cache refresh failed"},
        status_code=500,
    )


# --- /health endpoint (returns 503 if unhealthy) ---


@router.get("/health")
async def health():
    """Health check — returns 503 if critical dependencies are unreachable."""
    if _drain_mode:
        return JSONResponse(
            content={"status": "draining"},
            status_code=503,
        )

    checks: dict[str, str] = {}

    # RDS check
    try:
        from rds_module import execute_query

        execute_query("SELECT 1;")
        checks["rds"] = "ok"
    except Exception:
        checks["rds"] = "error"

    # Kafka check
    try:
        from kafka_module import health_check

        health_check()
        checks["kafka"] = "ok"
    except Exception:
        checks["kafka"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    status_text = "healthy" if all_ok else "unhealthy"
    return JSONResponse(
        content={"status": status_text, "checks": checks},
        status_code=status_code,
    )


# --- Additional /ops/* SRE Diagnostic Endpoints ---


def _percentile(data: list[float], pct: float) -> float:
    """Calculate percentile from sorted data."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    idx = min(idx, len(sorted_data) - 1)
    return round(sorted_data[idx], 2)


@router.get("/ops/status")
async def ops_status():
    """Composite status rollup — healthy, degraded, or unhealthy."""
    # Dependency health
    dep_ok = True
    try:
        from rds_module import execute_query

        execute_query("SELECT 1;")
    except Exception:
        dep_ok = False

    try:
        from kafka_module import health_check

        health_check()
    except Exception:
        dep_ok = False

    # Error rate
    uptime = time.monotonic() - _start_time
    error_rate = (_error_count / _request_count * 100) if _request_count > 0 else 0.0

    # Latency p99
    latencies = list(_request_latencies)
    p99 = _percentile(latencies, 99) if latencies else 0.0

    if _drain_mode:
        verdict = "unhealthy"
    elif not dep_ok or error_rate > 10.0:
        verdict = "degraded"
    else:
        verdict = "healthy"

    return JSONResponse(
        content={
            "status": verdict,
            "uptime_seconds": round(uptime, 1),
            "request_count": _request_count,
            "error_count": _error_count,
            "error_rate_pct": round(error_rate, 2),
            "latency_p99_ms": p99,
            "dependencies_ok": dep_ok,
            "drain_mode": _drain_mode,
        }
    )


@router.get("/ops/metrics")
async def ops_metrics():
    """Golden Signals and RED metrics from in-process counters."""
    uptime = time.monotonic() - _start_time
    latencies = list(_request_latencies)

    # Golden Signals
    traffic_rate = round(_request_count / uptime, 2) if uptime > 0 else 0.0
    error_pct = (
        round((_error_count / _request_count * 100), 2) if _request_count > 0 else 0.0
    )

    return JSONResponse(
        content={
            "golden_signals": {
                "latency": {
                    "p50_ms": _percentile(latencies, 50),
                    "p95_ms": _percentile(latencies, 95),
                    "p99_ms": _percentile(latencies, 99),
                },
                "traffic": {
                    "total_requests": _request_count,
                    "requests_per_second": traffic_rate,
                },
                "errors": {
                    "total_errors": _error_count,
                    "error_rate_pct": error_pct,
                },
                "saturation": {
                    "cache_entries": blacklist_cache.entry_count,
                    "recent_errors_buffer": len(_recent_errors),
                },
            },
            "red": {
                "rate": traffic_rate,
                "errors": _error_count,
                "duration": {
                    "p50_ms": _percentile(latencies, 50),
                    "p95_ms": _percentile(latencies, 95),
                    "p99_ms": _percentile(latencies, 99),
                },
            },
            "uptime_seconds": round(uptime, 1),
        }
    )


@router.post("/ops/drain")
async def ops_drain(request: Request):
    """Enable/disable drain mode. Health checks return 503 when draining."""
    global _drain_mode
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={"error": "invalid_payload", "message": "Invalid JSON body"},
            status_code=400,
        )
    _drain_mode = body.get("enabled", True)
    LOGGER.info("Drain mode set to %s", _drain_mode)
    return JSONResponse(content={"status": "ok", "drain_mode": _drain_mode})


@router.post("/ops/cache/flush")
async def ops_cache_flush():
    """Flush and refresh blacklist cache from RDS (alias for /ops/cache/refresh)."""
    LOGGER.info("ops/cache/flush triggered")
    success = blacklist_cache.refresh()
    if success:
        return JSONResponse(
            content={
                "status": "ok",
                "message": "Cache flushed and refreshed",
                "entries": blacklist_cache.entry_count,
            }
        )
    return JSONResponse(
        content={"status": "error", "message": "Cache flush failed"},
        status_code=500,
    )


@router.post("/ops/circuits")
async def ops_circuits():
    """Circuit breaker status. No app-managed circuits — returns static info."""
    return JSONResponse(
        content={
            "circuits": {
                "rds": {
                    "state": "closed",
                    "note": "Connection managed by rds_module",
                },
                "kafka": {
                    "state": "closed",
                    "note": "Connection managed by kafka_module",
                },
            },
            "message": (
                "No application-managed circuit breakers."
                " External module connections managed by"
                " their respective modules."
            ),
        }
    )


@router.post("/ops/loglevel")
async def ops_loglevel(request: Request):
    """Change log level at runtime (canonical /ops/loglevel path)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content={"error": "invalid_payload", "message": "Invalid JSON body"},
            status_code=400,
        )

    level_name = body.get("level", "").upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if level_name not in valid_levels:
        return JSONResponse(
            content={
                "error": "invalid_level",
                "message": f"Level must be one of {valid_levels}",
            },
            status_code=400,
        )

    numeric_level = getattr(logging, level_name)
    logging.getLogger().setLevel(numeric_level)
    LOGGER.info("Log level changed to %s", level_name)
    return JSONResponse(content={"status": "ok", "level": level_name})


@router.get("/ops/scale")
async def ops_scale():
    """Scaling information. KEDA manages autoscaling externally."""
    return JSONResponse(
        content={
            "scaling": {
                "strategy": "KEDA (external HPA)",
                "min_replicas": 1,
                "max_replicas": 500,
                "note": (
                    "Scaling managed by KEDA ScaledObject"
                    " in Helm chart, not application-managed."
                ),
            },
        }
    )
