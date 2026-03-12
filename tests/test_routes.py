"""Tests for app.routes — POST / and GET /status."""

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app


@pytest.fixture
def app():
    """Create a test FastAPI app."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_returns_ok(self, client):
        response = await client.get("/status")
        assert response.status_code == 200
        assert response.text == "OK"


class TestSendRequestEndpoint:
    @pytest.mark.asyncio
    async def test_valid_request_returns_ok(
        self, client, sample_nativeapp_payload, mock_security_hash, mock_kafka_module
    ):
        response = await client.post(
            "/?tvid=VZR2023A7F4E9B01&client=smartcast&h=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6&EventType=NATIVEAPP_TELEMETRY&timestamp=1700000000000",
            json=sample_nativeapp_payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self, client):
        response = await client.post(
            "/?tvid=VZR2023A7F4E9B01",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_params_returns_400(self, client, mock_security_hash):
        incomplete_payload = {"TvEvent": {"tvid": "VZR2023A7F4E9B01"}}
        response = await client.post(
            "/?tvid=VZR2023A7F4E9B01",
            json=incomplete_payload,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_security_hash_returns_400(
        self, client, sample_nativeapp_payload, mock_security_hash
    ):
        mock_security_hash.security_hash_match.return_value = False
        response = await client.post(
            "/?tvid=VZR2023A7F4E9B01&client=smartcast&h=badhash&EventType=NATIVEAPP_TELEMETRY&timestamp=1700000000000",
            json=sample_nativeapp_payload,
        )
        assert response.status_code == 400
