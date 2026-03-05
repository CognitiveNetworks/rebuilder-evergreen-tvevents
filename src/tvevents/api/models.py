"""Pydantic request / response models with realistic ``json_schema_extra`` examples.

Every model carries a full example so that the auto-generated OpenAPI spec
(``/docs``, ``/openapi.json``) is immediately useful for integration testing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Request models ───────────────────────────────────────────────────────


class TvEventEnvelope(BaseModel):
    """The ``TvEvent`` wrapper inside an ingestion request."""

    tvid: str = Field(..., description="Unique TV identifier (MAC-like)")
    client: str = Field(..., description="Client identifier")
    h: str = Field(..., description="HMAC-SHA256 security hash of tvid")
    EventType: str = Field(..., description="Event type discriminator")
    timestamp: int | float = Field(..., description="Unix timestamp in milliseconds")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tvid": "ITV00C000000000000001",
                    "client": "smartcast",
                    "h": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                    "EventType": "ACR_TUNER_DATA",
                    "timestamp": 1709568000000,
                }
            ]
        }
    }


class EventDataModel(BaseModel):
    """Generic ``EventData`` pass-through — event-type-specific keys vary."""

    model_config = {
        "extra": "allow",
        "json_schema_extra": {
            "examples": [
                {
                    "channelData": {
                        "majorId": 704,
                        "minorId": 1,
                        "channelId": "12345",
                        "channelName": "CNN",
                    },
                    "programData": {
                        "programId": "EP012345678901",
                        "startTime": 1709564400,
                    },
                    "resolution": {"vRes": 1080, "hRes": 1920},
                }
            ]
        },
    }


class EventIngestionRequest(BaseModel):
    """Full request body for ``POST /v1/events``."""

    TvEvent: dict[str, Any] = Field(
        ...,
        description="TV event envelope with device ID, HMAC hash, event type, and timestamp",
    )
    EventData: dict[str, Any] = Field(
        ...,
        description="Event-type-specific data payload",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "TvEvent": {
                        "tvid": "ITV00C000000000000001",
                        "client": "smartcast",
                        "h": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                        "EventType": "ACR_TUNER_DATA",
                        "timestamp": 1709568000000,
                        "appId": "com.vizio.smartcast",
                        "Namespace": "vizio.acr",
                    },
                    "EventData": {
                        "channelData": {
                            "majorId": 704,
                            "minorId": 1,
                            "channelId": "12345",
                            "channelName": "CNN",
                        },
                        "programData": {
                            "programId": "EP012345678901",
                            "startTime": 1709564400,
                        },
                        "resolution": {"vRes": 1080, "hRes": 1920},
                    },
                }
            ]
        }
    }


# ── Response models ──────────────────────────────────────────────────────


class EventIngestionResponse(BaseModel):
    """Successful ingestion response."""

    status: str = Field("accepted", description="Ingestion status")
    event_id: str = Field(..., description="Server-assigned event ID (UUID4)")
    event_type: str = Field(..., description="The EventType that was ingested")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "accepted",
                    "event_id": "c7e8f9a0-1b2c-3d4e-5f6a-7b8c9d0e1f2a",
                    "event_type": "ACR_TUNER_DATA",
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Error response returned to the caller."""

    error: str = Field(..., description="Error type / class name")
    message: str = Field(..., description="Human-readable description")
    request_id: str | None = Field(None, description="Correlation ID for tracing")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": "TvEventsSecurityValidationError",
                    "message": "Security hash decryption failure for tvid=ITV00C000000000000001.",
                    "request_id": "c7e8f9a0-1b2c-3d4e-5f6a-7b8c9d0e1f2a",
                }
            ]
        }
    }


class HealthCheckDetail(BaseModel):
    """Per-dependency health status."""

    status: str = Field(..., description="'healthy' or 'unhealthy'")
    latency_ms: float | None = Field(None, description="Check latency in ms")
    error: str | None = Field(None, description="Error message if unhealthy")


class HealthResponse(BaseModel):
    """Response for ``GET /health``."""

    status: str = Field(..., description="Overall status: 'healthy' or 'unhealthy'")
    checks: dict[str, HealthCheckDetail] = Field(..., description="Per-dependency health")
    version: str = Field(..., description="Service version")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "checks": {
                        "kafka": {"status": "healthy", "latency_ms": 2.3, "error": None},
                        "rds": {"status": "healthy", "latency_ms": 5.1, "error": None},
                        "redis": {"status": "healthy", "latency_ms": 0.8, "error": None},
                    },
                    "version": "1.0.0",
                }
            ]
        }
    }


# ── Ops response models ─────────────────────────────────────────────────


class StatusResponse(BaseModel):
    """``GET /ops/status`` — uptime and environment info."""

    service: str
    version: str
    environment: str
    uptime_seconds: float
    drain_mode: bool

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "service": "rebuilder-evergreen-tvevents",
                    "version": "1.0.0",
                    "environment": "production",
                    "uptime_seconds": 86412.7,
                    "drain_mode": False,
                }
            ]
        }
    }


class LatencyMetrics(BaseModel):
    """Latency percentile bucket."""

    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0


class GoldenSignals(BaseModel):
    """Golden Signals metrics."""

    latency: LatencyMetrics
    traffic_total: int = 0
    traffic_per_sec: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0
    saturation: dict[str, float] = Field(default_factory=dict)


class RedMetrics(BaseModel):
    """RED (Rate, Errors, Duration) metrics."""

    rate: float = 0.0
    errors: float = 0.0
    duration_p50: float = 0.0
    duration_p95: float = 0.0
    duration_p99: float = 0.0


class MetricsResponse(BaseModel):
    """``GET /ops/metrics`` — Golden Signals + RED."""

    golden_signals: GoldenSignals
    red: RedMetrics
    by_endpoint: dict[str, RedMetrics] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "golden_signals": {
                        "latency": {"p50": 3.2, "p95": 12.8, "p99": 45.1},
                        "traffic_total": 1048576,
                        "traffic_per_sec": 892.4,
                        "error_count": 127,
                        "error_rate": 0.00012,
                        "saturation": {
                            "kafka_queue": 0.05,
                            "rds_pool": 0.32,
                            "redis_pool": 0.11,
                        },
                    },
                    "red": {
                        "rate": 892.4,
                        "errors": 0.00012,
                        "duration_p50": 3.2,
                        "duration_p95": 12.8,
                        "duration_p99": 45.1,
                    },
                    "by_endpoint": {
                        "POST /v1/events": {
                            "rate": 890.1,
                            "errors": 0.00011,
                            "duration_p50": 3.1,
                            "duration_p95": 12.5,
                            "duration_p99": 44.8,
                        }
                    },
                }
            ]
        }
    }


class ConfigResponse(BaseModel):
    """``GET /ops/config`` — sanitised configuration (secrets redacted)."""

    config: dict[str, Any]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "config": {
                        "service_name": "rebuilder-evergreen-tvevents",
                        "zoo": "production",
                        "debug": False,
                        "log_level": "INFO",
                        "t1_salt": "***REDACTED***",
                        "rds_host": "tvevents-rds.us-east-1.rds.amazonaws.com",
                        "rds_pass": "***REDACTED***",
                        "kafka_bootstrap_servers": "msk-broker-1.us-east-1.amazonaws.com:9092",
                        "kafka_sasl_password": "***REDACTED***",
                        "redis_password": "***REDACTED***",
                    }
                }
            ]
        }
    }


class DependencyStatus(BaseModel):
    """Single dependency status."""

    name: str
    type: str
    status: str
    latency_ms: float | None = None
    error: str | None = None


class DependenciesResponse(BaseModel):
    """``GET /ops/dependencies`` — all dependency health."""

    dependencies: list[DependencyStatus]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "dependencies": [
                        {
                            "name": "kafka",
                            "type": "message_queue",
                            "status": "healthy",
                            "latency_ms": 2.3,
                            "error": None,
                        },
                        {
                            "name": "rds",
                            "type": "database",
                            "status": "healthy",
                            "latency_ms": 5.1,
                            "error": None,
                        },
                        {
                            "name": "redis",
                            "type": "cache",
                            "status": "healthy",
                            "latency_ms": 0.8,
                            "error": None,
                        },
                    ]
                }
            ]
        }
    }


class ErrorEntry(BaseModel):
    """A single recent error."""

    timestamp: str
    error_type: str
    message: str
    endpoint: str | None = None
    tvid: str | None = None


class ErrorsResponse(BaseModel):
    """``GET /ops/errors`` — circular buffer of recent errors."""

    errors: list[ErrorEntry]
    total: int

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "errors": [
                        {
                            "timestamp": "2026-03-04T12:00:00Z",
                            "error_type": "TvEventsSecurityValidationError",
                            "message": "Security hash decryption failure.",
                            "endpoint": "POST /v1/events",
                            "tvid": "ITV00C000000000000001",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    }


class DrainResponse(BaseModel):
    """``POST /ops/drain`` — toggle drain mode."""

    drain_mode: bool
    message: str

    model_config = {
        "json_schema_extra": {"examples": [{"drain_mode": True, "message": "Drain mode enabled"}]}
    }


class CacheFlushResponse(BaseModel):
    """``POST /ops/cache/flush`` — flush blacklist cache result."""

    flushed: bool
    message: str

    model_config = {
        "json_schema_extra": {
            "examples": [{"flushed": True, "message": "Blacklist cache flushed successfully"}]
        }
    }


class CircuitState(BaseModel):
    """Single circuit breaker state."""

    name: str
    state: str  # "closed", "open", "half-open"


class CircuitsResponse(BaseModel):
    """``POST /ops/circuits`` — circuit breaker state."""

    circuits: list[CircuitState]
    message: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "circuits": [
                        {"name": "kafka", "state": "closed"},
                        {"name": "rds", "state": "closed"},
                        {"name": "redis", "state": "closed"},
                    ],
                    "message": "Circuit states updated",
                }
            ]
        }
    }


class LogLevelResponse(BaseModel):
    """``PUT /ops/loglevel`` — log level change result."""

    previous: str
    current: str
    message: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "previous": "INFO",
                    "current": "DEBUG",
                    "message": "Log level changed to DEBUG",
                }
            ]
        }
    }


class ScaleResponse(BaseModel):
    """``POST /ops/scale`` — advisory scaling recommendation."""

    recommended_replicas: int
    current_rps: float
    message: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "recommended_replicas": 12,
                    "current_rps": 8500.0,
                    "message": "Advisory: scaling recommendation based on current traffic",
                }
            ]
        }
    }
