"""Tests for app.routes — /ops/* SRE endpoints."""

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


class TestOpsHealth:
    @pytest.mark.asyncio
    async def test_ops_health_returns_status(
        self, client, mock_rds_module, mock_kafka_module
    ):
        mock_rds_module.execute_query.return_value = [(1,)]
        mock_kafka_module.health_check.return_value = True
        response = await client.get("/ops/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "checks" in data


class TestOpsConfig:
    @pytest.mark.asyncio
    async def test_ops_config_returns_config(self, client):
        response = await client.get("/ops/config")
        assert response.status_code == 200
        data = response.json()
        assert "service_name" in data
        assert "event_types_enabled" in data


class TestOpsDependencies:
    @pytest.mark.asyncio
    async def test_ops_dependencies_returns_status(
        self, client, mock_rds_module, mock_kafka_module
    ):
        mock_rds_module.execute_query.return_value = [(1,)]
        mock_kafka_module.health_check.return_value = True
        response = await client.get("/ops/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert "dependencies" in data


class TestOpsCache:
    @pytest.mark.asyncio
    async def test_ops_cache_returns_statistics(self, client):
        response = await client.get("/ops/cache")
        assert response.status_code == 200
        data = response.json()
        assert "entry_count" in data


class TestOpsErrors:
    @pytest.mark.asyncio
    async def test_ops_errors_returns_summary(self, client):
        response = await client.get("/ops/errors")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "recent" in data


class TestOpsCacheRefresh:
    @pytest.mark.asyncio
    async def test_ops_cache_refresh_returns_result(self, client, mock_rds_module):
        mock_rds_module.execute_query.return_value = [
            {"channel_id": "ch1"},
            {"channel_id": "ch2"},
        ]
        response = await client.post("/ops/cache/refresh")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestOpsLogLevel:
    @pytest.mark.asyncio
    async def test_set_valid_log_level(self, client):
        response = await client.post("/ops/loglevel", json={"level": "DEBUG"})
        assert response.status_code == 200
        data = response.json()
        assert data["level"] == "DEBUG"

    @pytest.mark.asyncio
    async def test_set_invalid_log_level_returns_400(self, client):
        response = await client.post("/ops/loglevel", json={"level": "TRACE"})
        assert response.status_code == 400


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_200_when_healthy(
        self, client, mock_rds_module, mock_kafka_module
    ):
        mock_rds_module.execute_query.return_value = [(1,)]
        mock_kafka_module.health_check.return_value = True
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_returns_503_when_rds_down(
        self, client, mock_rds_module, mock_kafka_module
    ):
        mock_rds_module.execute_query.side_effect = Exception("connection refused")
        mock_kafka_module.health_check.return_value = True
        response = await client.get("/health")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_returns_503_when_draining(
        self, client, mock_rds_module, mock_kafka_module
    ):
        from app import routes

        routes._drain_mode = True
        try:
            response = await client.get("/health")
            assert response.status_code == 503
            assert response.json()["status"] == "draining"
        finally:
            routes._drain_mode = False


class TestOpsStatus:
    @pytest.mark.asyncio
    async def test_ops_status_returns_verdict(
        self, client, mock_rds_module, mock_kafka_module
    ):
        mock_rds_module.execute_query.return_value = [(1,)]
        mock_kafka_module.health_check.return_value = True
        response = await client.get("/ops/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert "uptime_seconds" in data
        assert "request_count" in data

    @pytest.mark.asyncio
    async def test_ops_status_degraded_when_deps_fail(
        self, client, mock_rds_module, mock_kafka_module
    ):
        mock_rds_module.execute_query.side_effect = Exception("down")
        mock_kafka_module.health_check.side_effect = Exception("down")
        response = await client.get("/ops/status")
        data = response.json()
        assert data["status"] in ("degraded", "unhealthy")


class TestOpsMetrics:
    @pytest.mark.asyncio
    async def test_ops_metrics_returns_golden_signals(self, client):
        response = await client.get("/ops/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "golden_signals" in data
        assert "latency" in data["golden_signals"]
        assert "traffic" in data["golden_signals"]
        assert "errors" in data["golden_signals"]
        assert "saturation" in data["golden_signals"]
        assert "red" in data
        assert "uptime_seconds" in data


class TestOpsDrain:
    @pytest.mark.asyncio
    async def test_enable_drain_mode(self, client):
        from app import routes

        try:
            response = await client.post("/ops/drain", json={"enabled": True})
            assert response.status_code == 200
            assert response.json()["drain_mode"] is True
        finally:
            routes._drain_mode = False

    @pytest.mark.asyncio
    async def test_disable_drain_mode(self, client):
        from app import routes

        routes._drain_mode = True
        try:
            response = await client.post("/ops/drain", json={"enabled": False})
            assert response.status_code == 200
            assert response.json()["drain_mode"] is False
        finally:
            routes._drain_mode = False

    @pytest.mark.asyncio
    async def test_drain_invalid_json_returns_400(self, client):
        response = await client.post(
            "/ops/drain",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400


class TestOpsCacheFlush:
    @pytest.mark.asyncio
    async def test_cache_flush_success(self, client, mock_rds_module):
        mock_rds_module.execute_query.return_value = [{"channel_id": "ch1"}]
        response = await client.post("/ops/cache/flush")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_cache_flush_failure(self, client, mock_rds_module):
        mock_rds_module.execute_query.side_effect = Exception("db error")
        response = await client.post("/ops/cache/flush")
        assert response.status_code == 500


class TestOpsCircuits:
    @pytest.mark.asyncio
    async def test_circuits_returns_state(self, client):
        response = await client.post("/ops/circuits")
        assert response.status_code == 200
        data = response.json()
        assert "circuits" in data
        assert "rds" in data["circuits"]
        assert "kafka" in data["circuits"]


class TestOpsLoglevelCanonical:
    @pytest.mark.asyncio
    async def test_set_valid_loglevel(self, client):
        response = await client.post("/ops/loglevel", json={"level": "WARNING"})
        assert response.status_code == 200
        assert response.json()["level"] == "WARNING"

    @pytest.mark.asyncio
    async def test_set_invalid_loglevel_returns_400(self, client):
        response = await client.post("/ops/loglevel", json={"level": "VERBOSE"})
        assert response.status_code == 400


class TestOpsScale:
    @pytest.mark.asyncio
    async def test_scale_returns_info(self, client):
        response = await client.get("/ops/scale")
        assert response.status_code == 200
        data = response.json()
        assert "scaling" in data
        assert data["scaling"]["strategy"] == "KEDA (external HPA)"
