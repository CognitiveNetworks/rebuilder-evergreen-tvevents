"""Tests for tvevents /ops/* endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient


class TestOpsStatus:
    """Tests for GET /ops/status."""

    def test_returns_healthy(self, client: TestClient) -> None:
        with patch("tvevents.api.ops.get_rds_client") as mock_rds:
            mock_rds.return_value.health_check.return_value = True
            response = client.get("/ops/status")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "healthy"
            assert body["service"] == "tvevents-k8s"
            assert "uptime_seconds" in body

    def test_returns_degraded_when_rds_down(self, client: TestClient) -> None:
        with patch("tvevents.api.ops.get_rds_client") as mock_rds:
            mock_rds.return_value.health_check.return_value = False
            response = client.get("/ops/status")
            assert response.status_code == 200
            assert response.json()["status"] == "degraded"


class TestOpsHealth:
    """Tests for GET /ops/health."""

    def test_returns_dependency_status(self, client: TestClient) -> None:
        with patch("tvevents.api.ops.get_rds_client") as mock_rds, \
             patch("tvevents.api.ops.get_kafka_producer") as mock_kafka:
            mock_rds.return_value.health_check.return_value = True
            response = client.get("/ops/health")
            assert response.status_code == 200
            body = response.json()
            assert "dependencies" in body
            assert any(d["name"] == "rds" for d in body["dependencies"])


class TestOpsMetrics:
    """Tests for GET /ops/metrics."""

    def test_returns_metrics(self, client: TestClient) -> None:
        response = client.get("/ops/metrics")
        assert response.status_code == 200
        body = response.json()
        assert "golden_signals" in body
        assert "red" in body


class TestOpsConfig:
    """Tests for GET /ops/config."""

    def test_returns_config_no_secrets(self, client: TestClient) -> None:
        response = client.get("/ops/config")
        assert response.status_code == 200
        body = response.json()
        assert body["service_name"] == "tvevents-k8s"
        assert "rds_pass" not in body
        assert "t1_salt" not in body
        assert "kafka_sasl_password" not in body


class TestOpsDependencies:
    """Tests for GET /ops/dependencies."""

    def test_returns_dependencies(self, client: TestClient) -> None:
        with patch("tvevents.api.ops.get_rds_client") as mock_rds, \
             patch("tvevents.api.ops.get_kafka_producer") as mock_kafka:
            mock_rds.return_value.health_check.return_value = True
            response = client.get("/ops/dependencies")
            assert response.status_code == 200
            assert "dependencies" in response.json()


class TestOpsErrors:
    """Tests for GET /ops/errors."""

    def test_returns_empty_errors(self, client: TestClient) -> None:
        response = client.get("/ops/errors")
        assert response.status_code == 200
        body = response.json()
        assert body["total_errors"] >= 0
        assert isinstance(body["recent"], list)


class TestOpsDrain:
    """Tests for POST /ops/drain."""

    def test_toggle_drain(self, client: TestClient) -> None:
        import tvevents.api.ops as ops_mod
        ops_mod._draining = False

        response = client.post("/ops/drain")
        assert response.status_code == 200
        body = response.json()
        assert body["draining"] is True

        response = client.post("/ops/drain")
        body = response.json()
        assert body["draining"] is False

        # Reset
        ops_mod._draining = False


class TestOpsCacheFlush:
    """Tests for POST /ops/cache/flush."""

    def test_flush_succeeds(self, client: TestClient) -> None:
        with patch("tvevents.api.ops.get_blacklist_cache") as mock_cache, \
             patch("tvevents.api.ops.get_rds_client") as mock_rds:
            mock_cache.return_value.flush.return_value = None
            mock_cache.return_value.get_blacklisted_channel_ids.return_value = ["123"]
            response = client.post("/ops/cache/flush")
            assert response.status_code == 200
            assert response.json()["flushed"] is True


class TestOpsCircuits:
    """Tests for GET /ops/circuits."""

    def test_returns_circuit_state(self, client: TestClient) -> None:
        response = client.get("/ops/circuits")
        assert response.status_code == 200
        body = response.json()
        assert body["circuits"]["rds"] == "closed"
        assert body["circuits"]["kafka"] == "closed"


class TestOpsLogLevel:
    """Tests for POST /ops/loglevel."""

    def test_change_log_level(self, client: TestClient) -> None:
        response = client.post("/ops/loglevel", json={"level": "DEBUG"})
        assert response.status_code == 200
        body = response.json()
        assert body["current"] == "DEBUG"

    def test_invalid_log_level_unchanged(self, client: TestClient) -> None:
        response = client.post("/ops/loglevel", json={"level": "INFO"})
        previous = response.json()["current"]
        response = client.post("/ops/loglevel", json={"level": "INVALID"})
        assert response.json()["current"] == previous


class TestOpsScale:
    """Tests for POST /ops/scale."""

    def test_returns_hpa_message(self, client: TestClient) -> None:
        response = client.post("/ops/scale")
        assert response.status_code == 200
        assert "Kubernetes HPA" in response.json()["message"]
