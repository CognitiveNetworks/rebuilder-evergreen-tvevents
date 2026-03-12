"""
Initialization steps for evergreen-tvevents application.
"""

import logging
import os
from contextlib import asynccontextmanager

from cnlib.cnlib import log
from fastapi import FastAPI

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import get_meter, set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


# Calculate Log Level
def compute_valid_log_level(level):
    """Return a valid logging level, defaulting to DEBUG for unknowns."""
    level = logging.getLevelName(level)
    if isinstance(level, str) and level.startswith("Level "):
        level = logging.DEBUG
    return level


log_level = compute_valid_log_level(os.environ.get("LOG_LEVEL", "DEBUG"))
logger_provider = LoggerProvider()
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
otel_handler = LoggingHandler(level=log_level, logger_provider=logger_provider)
set_logger_provider(logger_provider)


def configure_logging():
    """Configure and return the application logger with OTEL handler."""
    logger = log.getLogger(__name__)
    logger.setLevel(log_level)
    logger.addHandler(otel_handler)
    return logger


# Metrics Meter
service_name = os.getenv("SERVICE_NAME", "evergreen-tvevents")
resource = Resource.create({"service.name": service_name})
metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
set_meter_provider(meter_provider)
meter = get_meter(__name__)


LOGGER = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize blacklist cache on startup."""
    from app.blacklist import blacklist_cache

    LOGGER.info("evergreen-tvevents service starting")
    blacklist_cache.initialize()
    LOGGER.info("evergreen-tvevents service started")
    yield
    LOGGER.info("evergreen-tvevents service shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = trace.get_tracer_provider()
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # type: ignore[attr-defined]

    app = FastAPI(
        title="evergreen-tvevents",
        description="TV telemetry ingestion microservice",
        lifespan=lifespan,
    )

    from app.routes import log_request_middleware, metrics_middleware, router

    app.middleware("http")(metrics_middleware)
    app.middleware("http")(log_request_middleware)
    app.include_router(router)

    FastAPIInstrumentor.instrument_app(app)

    return app
