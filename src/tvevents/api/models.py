"""Pydantic request/response models for tvevents-k8s API."""


from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- Ingestion Models ---


class IngestResponse(BaseModel):
    """Response from POST / ingestion endpoint."""

    status: str = "OK"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"status": "OK"}]
        }
    )


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": "TvEventsMissingRequiredParamError",
                    "detail": "Missing Required Param: tvid",
                }
            ]
        }
    )


# --- /ops/* Response Models ---


class DependencyStatus(BaseModel):
    """Health status of a single dependency."""

    name: str
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None


class OpsStatusResponse(BaseModel):
    """Composite health verdict."""

    status: str = Field(description="healthy | degraded | unhealthy")
    service: str
    version: str
    uptime_seconds: float

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "healthy",
                    "service": "tvevents-k8s",
                    "version": "0.1.0",
                    "uptime_seconds": 3600.0,
                }
            ]
        }
    )


class OpsHealthResponse(BaseModel):
    """Dependency-aware health check."""

    status: str
    dependencies: list[DependencyStatus]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "healthy",
                    "dependencies": [
                        {"name": "rds", "healthy": True, "latency_ms": 5.2},
                        {"name": "kafka", "healthy": True, "latency_ms": 2.1},
                    ],
                }
            ]
        }
    )


class OpsMetricsResponse(BaseModel):
    """Golden Signals + RED metrics."""

    golden_signals: dict[str, Any]
    red: dict[str, Any]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "golden_signals": {
                        "latency_p50_ms": 12.5,
                        "latency_p95_ms": 45.0,
                        "latency_p99_ms": 120.0,
                        "traffic_total_requests": 150000,
                        "errors_total": 15,
                        "errors_by_status": {"400": 10, "500": 5},
                        "saturation_in_flight": 3,
                    },
                    "red": {
                        "rate_total": 150000,
                        "errors_ratio": 0.0001,
                        "duration_p50_ms": 12.5,
                        "duration_p95_ms": 45.0,
                        "duration_p99_ms": 120.0,
                    },
                }
            ]
        }
    )


class OpsConfigResponse(BaseModel):
    """Runtime configuration (secrets redacted)."""

    env: str
    service_name: str
    aws_region: str
    send_evergreen: bool
    send_legacy: bool
    tvevents_debug: bool
    kafka_bootstrap_servers: str
    kafka_topics: list[str]
    debug_kafka_topics: list[str]
    rds_host: str
    rds_db: str
    log_level: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "env": "production",
                    "service_name": "tvevents-k8s",
                    "aws_region": "us-east-1",
                    "send_evergreen": True,
                    "send_legacy": True,
                    "tvevents_debug": False,
                    "kafka_bootstrap_servers": "kafka.internal:9092",
                    "kafka_topics": ["tveoe-evergreen", "tveoe-legacy"],
                    "debug_kafka_topics": [],
                    "rds_host": "rds.internal",
                    "rds_db": "tvevents",
                    "log_level": "INFO",
                }
            ]
        }
    )


class OpsDependenciesResponse(BaseModel):
    """Dependency connectivity status."""

    dependencies: list[DependencyStatus]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dependencies": [
                        {"name": "rds", "healthy": True, "latency_ms": 5.2},
                        {"name": "kafka", "healthy": True, "latency_ms": 2.1},
                    ]
                }
            ]
        }
    )


class ErrorEntry(BaseModel):
    """A single recent error."""

    timestamp: str
    error_type: str
    message: str


class OpsErrorsResponse(BaseModel):
    """Recent error summary."""

    total_errors: int
    recent: list[ErrorEntry]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total_errors": 3,
                    "recent": [
                        {
                            "timestamp": "2025-01-15T10:30:00Z",
                            "error_type": "TvEventsSecurityValidationError",
                            "message": "Security hash decryption failure for tvid=abc123",
                        }
                    ],
                }
            ]
        }
    )


class OpsDrainResponse(BaseModel):
    """Drain toggle response."""

    draining: bool
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"draining": True, "message": "Service is now draining"}]
        }
    )


class OpsCacheFlushResponse(BaseModel):
    """Cache flush response."""

    flushed: bool
    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"flushed": True, "message": "Blacklist cache flushed and reloaded"}
            ]
        }
    )


class OpsCircuitsResponse(BaseModel):
    """Circuit breaker state."""

    circuits: dict[str, str]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"circuits": {"rds": "closed", "kafka": "closed"}}]
        }
    )


class OpsLogLevelRequest(BaseModel):
    """Request body for log level change."""

    level: str = Field(description="DEBUG | INFO | WARNING | ERROR")

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"level": "DEBUG"}]}
    )


class OpsLogLevelResponse(BaseModel):
    """Log level change response."""

    previous: str
    current: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"previous": "INFO", "current": "DEBUG"}]
        }
    )


class OpsScaleResponse(BaseModel):
    """Scale response — not applicable for Kubernetes HPA."""

    message: str

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"message": "Scaling is managed by Kubernetes HPA, not the application"}
            ]
        }
    )
