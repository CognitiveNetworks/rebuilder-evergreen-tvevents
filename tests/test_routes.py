"""Route integration tests — POST /v1/events and GET /health.

Uses httpx.AsyncClient with TestTransport against the real FastAPI app
with mocked Kafka, RDS, Redis, and cache services.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tests.conftest import TVID_1


class TestSmartTvEventIngestion:
    """End-to-end route tests for the TV event ingestion endpoint.
    Sends realistic payloads through the full FastAPI handler and verifies
    HTTP status codes, response structure, and error details."""

    @pytest.mark.asyncio
    async def test_tv_sends_valid_acr_tuner_event_returns_success(
        self,
        app_client,
        sample_acr_tuner_payload: dict[str, Any],
    ) -> None:
        """TV ITV00C000000000000001 sends a complete ACR_TUNER_DATA payload
        with valid HMAC → service returns 200 with status='accepted'."""
        resp = await app_client.post(
            "/v1/events",
            params={"tvid": TVID_1, "event_type": "ACR_TUNER_DATA"},
            json=sample_acr_tuner_payload,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["event_type"] == "ACR_TUNER_DATA"
        assert "event_id" in body

    @pytest.mark.asyncio
    async def test_tv_sends_invalid_hash_returns_400_with_error_detail(
        self,
        app_client,
        sample_acr_tuner_payload: dict[str, Any],
    ) -> None:
        """TV sends payload with wrong HMAC hash → 400 response with
        error='TvEventsSecurityValidationError' and descriptive message."""
        payload = deepcopy(sample_acr_tuner_payload)
        payload["TvEvent"]["h"] = "0" * 64  # bogus hash
        resp = await app_client.post(
            "/v1/events",
            params={"tvid": TVID_1, "event_type": "ACR_TUNER_DATA"},
            json=payload,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "TvEventsSecurityValidationError"
        assert "Security hash decryption failure" in body["message"]

    @pytest.mark.asyncio
    async def test_tv_sends_missing_params_returns_400(
        self,
        app_client,
        sample_acr_tuner_payload: dict[str, Any],
    ) -> None:
        """TV sends payload with tvid removed from TvEvent → 400 with
        MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["TvEvent"]["tvid"]
        resp = await app_client.post(
            "/v1/events",
            params={"tvid": TVID_1, "event_type": "ACR_TUNER_DATA"},
            json=payload,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "TvEventsMissingRequiredParamError"

    @pytest.mark.asyncio
    async def test_tv_sends_platform_telemetry_returns_success(
        self,
        app_client,
        sample_platform_telemetry_payload: dict[str, Any],
    ) -> None:
        """TV sends valid PLATFORM_TELEMETRY payload → 200 accepted."""
        resp = await app_client.post(
            "/v1/events",
            params={"tvid": TVID_1, "event_type": "PLATFORM_TELEMETRY"},
            json=sample_platform_telemetry_payload,
        )
        assert resp.status_code == 200
        assert resp.json()["event_type"] == "PLATFORM_TELEMETRY"

    @pytest.mark.asyncio
    async def test_tv_sends_nativeapp_telemetry_returns_success(
        self,
        app_client,
        sample_nativeapp_telemetry_payload: dict[str, Any],
    ) -> None:
        """TV sends valid NATIVEAPP_TELEMETRY payload → 200 accepted."""
        resp = await app_client.post(
            "/v1/events",
            params={"tvid": TVID_1, "event_type": "NATIVEAPP_TELEMETRY"},
            json=sample_nativeapp_telemetry_payload,
        )
        assert resp.status_code == 200
        assert resp.json()["event_type"] == "NATIVEAPP_TELEMETRY"

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_healthy_when_all_deps_up(
        self,
        app_client,
    ) -> None:
        """GET /health → 200 with status='healthy' when Kafka, RDS, and
        Redis mock health checks all return True."""
        resp = await app_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_503_when_kafka_down(
        self,
        settings,
        mock_rds_client,
        mock_redis_client,
        mock_cache_service,
    ) -> None:
        """GET /health → 503 when Kafka health_check returns False."""
        from httpx import ASGITransport, AsyncClient

        from tests.conftest import _build_test_app

        bad_kafka = AsyncMock()
        bad_kafka.health_check = AsyncMock(return_value=False)
        bad_kafka.send = AsyncMock()
        bad_kafka.close = AsyncMock()

        app = _build_test_app(
            settings, bad_kafka, mock_rds_client, mock_redis_client, mock_cache_service
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
