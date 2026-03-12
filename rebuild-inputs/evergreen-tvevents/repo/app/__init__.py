"""
Initialization steps for application
"""

import os
import logging
from flask import Flask

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import set_meter_provider, get_meter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry._logs import set_logger_provider

from cnlib.cnlib import log

# Get container or pod name from environment variables
# container_name = os.getenv('HOSTNAME', 'unknown-container')


# Calculate Log Level
def compute_valid_log_level(level):
    level = logging.getLevelName(level)
    if isinstance(level, str) and level.startswith("Level "):
        level = logging.DEBUG

    return level


log_level = compute_valid_log_level(os.environ.get('LOG_LEVEL', 'DEBUG'))
logger_provider = LoggerProvider()
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
otel_handler = LoggingHandler(level=log_level, logger_provider=logger_provider)
set_logger_provider(logger_provider)


def configure_logging():
    # Setup Logging
    logger = log.getLogger(__name__)
    logger.setLevel(log_level)

    # Setup OTEL logger
    logger.addHandler(otel_handler)
    return logger


# Metrics Meter
service_name = os.getenv("SERVICE_NAME", "default-service")
resource_m = Resource.create({"service.name": service_name})
metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
meter_provider = MeterProvider(resource=resource_m, metric_readers=[metric_reader])
set_meter_provider(meter_provider)
meter = get_meter(__name__)

LOGGER = configure_logging()


def create_app():

    # Initialize instrumentation
    Psycopg2Instrumentor().instrument()
    BotocoreInstrumentor().instrument()
    Boto3SQSInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    URLLib3Instrumentor().instrument()

    resource_t = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource_t)
    trace.set_tracer_provider(provider)
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)

    app = Flask(__name__)
    FlaskInstrumentor().instrument_app(app)

    with app.app_context():
        # pylint: disable=C0415
        from app.routes import init_routes
        from app.routes import bp as routes_bp

        app.register_blueprint(routes_bp)
        init_routes(app)

        LOGGER.info('tvevent api service started')
        LOGGER.debug('In Init')

    return app
