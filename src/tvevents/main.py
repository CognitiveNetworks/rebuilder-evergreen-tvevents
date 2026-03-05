"""FastAPI application factory — lifespan events, OTEL setup, router wiring.

The ``create_app`` factory returns a fully configured :class:`FastAPI`
instance with:

* OTEL tracing, metrics, and structured logging
* Kafka, RDS, Redis, and blacklist-cache services initialised on startup
* Graceful shutdown for every connection pool
* Exception handlers that surface domain errors as JSON
* Metrics middleware on every request
"""

from __future__ import annotations

import datetime
import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from tvevents import __version__
from tvevents.api.health import router as health_router
from tvevents.api.models import ErrorEntry, ErrorResponse
from tvevents.api.routes import router as events_router
from tvevents.config import Settings
from tvevents.domain.validation import (
    TvEventsCatchallException,
    TvEventsDefaultException,
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
    TvEventsSecurityValidationError,
)
from tvevents.middleware.metrics import MetricsMiddleware
from tvevents.ops.diagnostics import record_error
from tvevents.ops.diagnostics import router as diagnostics_router
from tvevents.ops.remediation import router as remediation_router
from tvevents.services.cache import BlacklistCacheService
from tvevents.services.kafka_producer import KafkaProducerService
from tvevents.services.rds_client import RdsClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


# ── OTEL bootstrap ───────────────────────────────────────────────────────


def _configure_otel(settings: Settings) -> None:
    """Set up OpenTelemetry tracing, metrics, and log export."""
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": __version__,
            "deployment.environment": settings.zoo,
        }
    )

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_exporter = OTLPMetricExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    set_meter_provider(meter_provider)

    # Logs
    log_exporter = OTLPLogExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)

    # Attach OTEL handler to root logger
    log_level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    otel_handler = LoggingHandler(level=log_level, logger_provider=logger_provider)
    logging.getLogger().addHandler(otel_handler)


# ── Structured logging ───────────────────────────────────────────────────


def _configure_logging(settings: Settings) -> None:
    """Set up structured JSON logging on stdout."""
    log_level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy libraries
    logging.getLogger("confluent_kafka").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)


# ── Lifespan ─────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup / shutdown of all external services."""
    settings: Settings = app.state.settings
    app.state.start_time = time.monotonic()
    app.state.drain_mode = False
    app.state.circuits = {"kafka": "closed", "rds": "closed", "redis": "closed"}

    _configure_logging(settings)
    _configure_otel(settings)

    logger.info(
        "Starting %s v%s (zoo=%s)",
        settings.service_name,
        __version__,
        settings.zoo,
    )

    # ── Kafka ────────────────────────────────────────────────────────
    kafka = KafkaProducerService(settings)
    try:
        await kafka.connect()
        app.state.kafka = kafka
    except Exception as exc:
        logger.error("Kafka producer init failed: %s", exc)
        app.state.kafka = None

    # ── RDS ──────────────────────────────────────────────────────────
    rds = RdsClient(settings)
    try:
        await rds.connect()
        app.state.rds = rds
    except Exception as exc:
        logger.error("RDS pool init failed: %s", exc)
        app.state.rds = None

    # ── Redis ────────────────────────────────────────────────────────
    try:
        redis_client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db,
            ssl=settings.redis_ssl,
            socket_timeout=5,
            socket_connect_timeout=5,
            decode_responses=False,
        )
        await redis_client.ping()  # type: ignore[misc]
        app.state.redis = redis_client
    except Exception as exc:
        logger.error("Redis init failed: %s", exc)
        app.state.redis = None
        redis_client = None

    # ── Blacklist cache ──────────────────────────────────────────────
    if app.state.rds is not None and redis_client is not None:
        cache = BlacklistCacheService(settings, rds, redis_client)
        try:
            await cache.refresh_cache()
            logger.info("Blacklist cache pre-populated")
        except Exception as exc:
            logger.error("Blacklist cache pre-population failed: %s", exc)
        app.state.cache = cache
    else:
        app.state.cache = None
        logger.warning("Blacklist cache not available (RDS or Redis missing)")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down services…")

    if app.state.kafka is not None:
        await app.state.kafka.close()

    if app.state.rds is not None:
        await app.state.rds.close()

    if redis_client is not None:
        await redis_client.aclose()
        logger.info("Redis connection closed")

    logger.info("Shutdown complete")


# ── Exception handlers ───────────────────────────────────────────────────


def _make_error_response(
    request: Request,
    exc: Exception,
    status: int,
) -> JSONResponse:
    """Build a JSON error response and record the error."""
    error_type = type(exc).__name__
    message = str(exc)
    request_id = request.headers.get("x-request-id")

    # Suppress internal detail from external callers
    safe_message = message
    if status >= 500:
        safe_message = "Internal server error"
        logger.error("Unhandled %s: %s (request_id=%s)", error_type, message, request_id)
    else:
        logger.warning("%s: %s (request_id=%s)", error_type, message, request_id)

    record_error(
        ErrorEntry(
            timestamp=datetime.datetime.now(tz=datetime.UTC).isoformat(),
            error_type=error_type,
            message=message,
            endpoint=f"{request.method} {request.url.path}",
            tvid=request.query_params.get("tvid"),
        )
    )

    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=error_type,
            message=safe_message,
            request_id=request_id,
        ).model_dump(),
    )


# ── App factory ──────────────────────────────────────────────────────────


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: C901
    """Build and return the fully-wired FastAPI application."""
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="rebuilder-evergreen-tvevents",
        description="TV event telemetry ingestion service (rebuilt from legacy Flask/Firehose)",
        version=__version__,
        lifespan=lifespan,
    )

    app.state.settings = settings

    # ── Middleware ────────────────────────────────────────────────────
    app.add_middleware(MetricsMiddleware)

    # ── Routers ──────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(diagnostics_router)
    app.include_router(remediation_router)

    # ── Exception handlers ───────────────────────────────────────────

    @app.exception_handler(TvEventsMissingRequiredParamError)
    async def _missing_param(
        request: Request, exc: TvEventsMissingRequiredParamError
    ) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsSecurityValidationError)
    async def _security_error(
        request: Request, exc: TvEventsSecurityValidationError
    ) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsInvalidPayloadError)
    async def _invalid_payload(request: Request, exc: TvEventsInvalidPayloadError) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsCatchallException)
    async def _catchall(request: Request, exc: TvEventsCatchallException) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsDefaultException)
    async def _default(request: Request, exc: TvEventsDefaultException) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return _make_error_response(request, exc, 500)

    # ── Drain-mode guard ─────────────────────────────────────────────

    @app.middleware("http")
    async def drain_guard(request: Request, call_next: Any) -> Any:
        """Reject new ingestion requests when drain mode is active."""
        _exempt = ("/ops", "/health", "/docs", "/openapi.json")
        if getattr(request.app.state, "drain_mode", False) and not any(
            request.url.path.startswith(p) for p in _exempt
        ):
            return JSONResponse(
                status_code=503,
                content={"error": "ServiceDraining", "message": "Service is draining"},
            )
        return await call_next(request)

    # ── OTEL FastAPI instrumentation ─────────────────────────────────
    FastAPIInstrumentor.instrument_app(app)

    return app


# ── Module-level app instance for ``uvicorn tvevents.main:app`` ──────────
app: FastAPI = create_app()
