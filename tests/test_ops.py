"""SRE operational endpoint tests — /ops/* diagnostics and remediation.

Validates that every ops endpoint returns real data and that secrets
are properly redacted.
"""

from __future__ import annotations

import pytest


class TestSreOperationalEndpoints:
    """Verify the SRE ops endpoints respond correctly with real data
    from the mocked service dependencies."""

    @pytest.mark.asyncio
    async def test_ops_status_returns_uptime_and_version(self, app_client) -> None:
        """GET /ops/status → 200 with service name, version, uptime_seconds,
        and drain_mode=False."""
        resp = await app_client.get("/ops/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "rebuilder-evergreen-tvevents"
        assert "version" in body
        assert "uptime_seconds" in body
        assert isinstance(body["uptime_seconds"], (int, float))
        assert body["drain_mode"] is False

    @pytest.mark.asyncio
    async def test_ops_health_returns_dependency_details(self, app_client) -> None:
        """GET /ops/health → 200 with per-dependency status for kafka,
        rds, redis, and otel."""
        resp = await app_client.get("/ops/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "checks" in body
        checks = body["checks"]
        # Kafka, RDS, Redis should be present since mocks are configured
        for dep in ("kafka", "rds", "redis"):
            assert dep in checks

    @pytest.mark.asyncio
    async def test_ops_metrics_returns_real_golden_signals(self, app_client) -> None:
        """GET /ops/metrics → 200 with golden_signals containing latency,
        traffic, error fields — real data from the MetricsCollector."""
        resp = await app_client.get("/ops/metrics")
        assert resp.status_code == 200
        body = resp.json()
        gs = body["golden_signals"]
        assert "latency" in gs
        assert "traffic_total" in gs
        assert "traffic_per_sec" in gs
        assert "error_count" in gs
        assert "error_rate" in gs

    @pytest.mark.asyncio
    async def test_ops_config_redacts_secrets(self, app_client) -> None:
        """GET /ops/config → 200 with t1_salt, rds_pass, redis_password
        replaced by '***REDACTED***' — secrets never leak."""
        resp = await app_client.get("/ops/config")
        assert resp.status_code == 200
        body = resp.json()
        config = body["config"]
        for secret_field in ("t1_salt", "rds_pass", "redis_password", "kafka_sasl_password"):
            assert config[secret_field] == "***REDACTED***"
        # Non-secret fields should still appear
        assert config["service_name"] == "rebuilder-evergreen-tvevents"

    @pytest.mark.asyncio
    async def test_ops_dependencies_lists_all_deps(self, app_client) -> None:
        """GET /ops/dependencies → 200 with Kafka, RDS, Redis listed
        as dependencies with their status."""
        resp = await app_client.get("/ops/dependencies")
        assert resp.status_code == 200
        body = resp.json()
        dep_names = {d["name"] for d in body["dependencies"]}
        assert "kafka" in dep_names
        assert "rds" in dep_names
        assert "redis" in dep_names

    @pytest.mark.asyncio
    async def test_ops_errors_returns_recent_errors(self, app_client) -> None:
        """GET /ops/errors → 200 with an errors list (may be empty on
        first access, but the response structure must be correct)."""
        resp = await app_client.get("/ops/errors")
        assert resp.status_code == 200
        body = resp.json()
        assert "errors" in body
        assert isinstance(body["errors"], list)
        assert "total" in body

    @pytest.mark.asyncio
    async def test_ops_drain_sets_drain_mode(self, app_client) -> None:
        """POST /ops/drain with enabled=true → 200 with drain_mode=True,
        then POST with enabled=false → drain_mode=False."""
        resp = await app_client.post("/ops/drain", json={"enabled": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["drain_mode"] is True
        assert "enabled" in body["message"].lower() or "drain" in body["message"].lower()

        # Reset
        resp2 = await app_client.post("/ops/drain", json={"enabled": False})
        assert resp2.status_code == 200
        assert resp2.json()["drain_mode"] is False

    @pytest.mark.asyncio
    async def test_ops_cache_flush_clears_blacklist(self, app_client) -> None:
        """POST /ops/cache/flush → 200 with flushed=True, confirming
        the blacklist cache was cleared."""
        resp = await app_client.post("/ops/cache/flush")
        assert resp.status_code == 200
        body = resp.json()
        assert body["flushed"] is True

    @pytest.mark.asyncio
    async def test_ops_loglevel_changes_level(self, app_client) -> None:
        """PUT /ops/loglevel with level='DEBUG' → 200 with current='DEBUG'."""
        resp = await app_client.put("/ops/loglevel", json={"level": "DEBUG"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["current"] == "DEBUG"
        assert "previous" in body

    @pytest.mark.asyncio
    async def test_ops_circuits_opens_and_closes_breaker(self, app_client) -> None:
        """POST /ops/circuits with name='kafka', state='open' → 200 with the
        circuit listed as open.  Then close it and verify the state update."""
        resp = await app_client.post(
            "/ops/circuits", json={"name": "kafka", "state": "open"}
        )
        assert resp.status_code == 200
        body = resp.json()
        circuits_map = {c["name"]: c["state"] for c in body["circuits"]}
        assert circuits_map["kafka"] == "open"
        assert "kafka" in body["message"] and "open" in body["message"]

        # Close the circuit again
        resp2 = await app_client.post(
            "/ops/circuits", json={"name": "kafka", "state": "closed"}
        )
        assert resp2.status_code == 200
        circuits_map2 = {c["name"]: c["state"] for c in resp2.json()["circuits"]}
        assert circuits_map2["kafka"] == "closed"

    @pytest.mark.asyncio
    async def test_ops_scale_returns_advisory_recommendation(self, app_client) -> None:
        """POST /ops/scale → 200 with recommended_replicas (≥ 2), current_rps
        (float), and an advisory message — no actual scaling performed."""
        resp = await app_client.post("/ops/scale")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["recommended_replicas"], int)
        assert body["recommended_replicas"] >= 2
        assert isinstance(body["current_rps"], (int, float))
        assert "advisory" in body["message"].lower()
