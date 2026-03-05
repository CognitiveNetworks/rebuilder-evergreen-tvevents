"""Pydantic request / response model tests.

Validates that the API models parse correctly, include required fields,
and carry the right structure for OpenAPI consumers.
"""

from __future__ import annotations

from typing import Any

from tests.conftest import TVID_1, _make_hmac
from tvevents.api.models import (
    ErrorResponse,
    EventIngestionRequest,
    GoldenSignals,
    HealthCheckDetail,
    HealthResponse,
    LatencyMetrics,
    MetricsResponse,
    RedMetrics,
)


class TestPydanticRequestResponseModels:
    """Verify Pydantic models parse valid data, reject invalid data,
    and include required structural fields."""

    def test_event_ingestion_request_validates_correctly(self) -> None:
        """A full EventIngestionRequest with realistic TvEvent and
        EventData parses without error."""
        raw: dict[str, Any] = {
            "TvEvent": {
                "tvid": TVID_1,
                "client": "smartcast",
                "h": _make_hmac(TVID_1),
                "EventType": "ACR_TUNER_DATA",
                "timestamp": 1709568000000,
                "appId": "com.vizio.smartcast",
                "Namespace": "vizio.acr",
            },
            "EventData": {
                "channelData": {
                    "majorId": 45,
                    "minorId": 1,
                    "channelId": "10045",
                    "channelName": "PBS",
                },
            },
        }
        model = EventIngestionRequest(**raw)
        assert model.TvEvent["tvid"] == TVID_1
        assert model.EventData["channelData"]["majorId"] == 45

    def test_error_response_includes_request_id(self) -> None:
        """ErrorResponse carries error, message, and optional request_id."""
        resp = ErrorResponse(
            error="TvEventsSecurityValidationError",
            message="Security hash decryption failure for tvid=ITV00C000000000000001.",
            request_id="c7e8f9a0-1b2c-3d4e-5f6a-7b8c9d0e1f2a",
        )
        assert resp.error == "TvEventsSecurityValidationError"
        assert resp.request_id == "c7e8f9a0-1b2c-3d4e-5f6a-7b8c9d0e1f2a"
        assert "ITV00C000000000000001" in resp.message

    def test_health_response_structure(self) -> None:
        """HealthResponse has status, checks dict, and version fields."""
        resp = HealthResponse(
            status="healthy",
            checks={
                "kafka": HealthCheckDetail(status="healthy", latency_ms=2.3),
                "rds": HealthCheckDetail(status="healthy", latency_ms=5.1),
                "redis": HealthCheckDetail(status="healthy", latency_ms=0.8),
            },
            version="1.0.0",
        )
        assert resp.status == "healthy"
        assert len(resp.checks) == 3
        assert resp.checks["kafka"].latency_ms == 2.3
        assert resp.version == "1.0.0"

    def test_metrics_response_includes_golden_signals(self) -> None:
        """MetricsResponse contains golden_signals with latency, traffic,
        error fields, and a RED sub-model."""
        latency = LatencyMetrics(p50=3.2, p95=12.8, p99=45.1)
        golden = GoldenSignals(
            latency=latency,
            traffic_total=1048576,
            traffic_per_sec=892.4,
            error_count=127,
            error_rate=0.00012,
            saturation={"rds_pool": 0.32},
        )
        red = RedMetrics(
            rate=892.4,
            errors=0.00012,
            duration_p50=3.2,
            duration_p95=12.8,
            duration_p99=45.1,
        )
        resp = MetricsResponse(golden_signals=golden, red=red)
        assert resp.golden_signals.traffic_total == 1048576
        assert resp.golden_signals.latency.p50 == 3.2
        assert resp.red.rate == 892.4
        assert resp.golden_signals.saturation["rds_pool"] == 0.32
