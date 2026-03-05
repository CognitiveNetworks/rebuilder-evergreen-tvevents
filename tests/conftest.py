"""Shared test fixtures for rebuilder-evergreen-tvevents.

Provides realistic Vizio Smart TV payloads, HMAC computation, mocked
service dependencies, and a fully wired httpx.AsyncClient for route tests.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

# Set T1_SALT before any tvevents imports so that the module-level
# ``app = create_app()`` in main.py can instantiate Settings.
os.environ.setdefault("T1_SALT", "tvevents-test-salt-2024")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from tvevents.config import Settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator as AsyncGeneratorType  # noqa: N814

# ── Test salt & environment ──────────────────────────────────────────────

TEST_SALT = "tvevents-test-salt-2024"
TEST_ZOO = "test"


# ── Settings ─────────────────────────────────────────────────────────────


@pytest.fixture()
def settings() -> Settings:
    """Minimal Settings with test salt and zoo — no real secrets."""
    return Settings(
        t1_salt=TEST_SALT,
        zoo=TEST_ZOO,
        kafka_delivery_enabled=False,
        debug=False,
        log_level="WARNING",
    )


# ── HMAC helper ──────────────────────────────────────────────────────────


@pytest.fixture()
def valid_hmac_hash():
    """Return a callable that computes a real HMAC-SHA256 hex digest for a
    given *tvid* using the test salt.

    Usage in tests::

        h = valid_hmac_hash("ITV00C000000000000001")
    """

    def _compute(tvid: str) -> str:
        return hmac.new(TEST_SALT.encode(), tvid.encode(), hashlib.sha256).hexdigest()

    return _compute


# ── Realistic TV IDs ─────────────────────────────────────────────────────

TVID_1 = "ITV00C000000000000001"
TVID_2 = "ITV00CA1B2C3D4E5F60007"


# ── Payload factories ────────────────────────────────────────────────────


def _make_hmac(tvid: str) -> str:
    return hmac.new(TEST_SALT.encode(), tvid.encode(), hashlib.sha256).hexdigest()


@pytest.fixture()
def sample_acr_tuner_payload() -> dict[str, Any]:
    """Complete valid ACR_TUNER_DATA request payload with realistic data."""
    tvid = TVID_1
    return {
        "TvEvent": {
            "tvid": tvid,
            "client": "smartcast",
            "h": _make_hmac(tvid),
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
            "programData": {
                "programId": "EP012345678901",
                "startTime": 1709564400,
            },
            "resolution": {"vRes": 1080, "hRes": 1920},
        },
    }


@pytest.fixture()
def sample_platform_telemetry_payload() -> dict[str, Any]:
    """Complete valid PLATFORM_TELEMETRY request payload."""
    tvid = TVID_1
    return {
        "TvEvent": {
            "tvid": tvid,
            "client": "smartcast",
            "h": _make_hmac(tvid),
            "EventType": "PLATFORM_TELEMETRY",
            "timestamp": 1709568000000,
        },
        "EventData": {
            "PanelData": {
                "PanelState": "ON",
                "Timestamp": 1709568000000,
                "WakeupReason": 0,
            },
        },
    }


@pytest.fixture()
def sample_nativeapp_telemetry_payload() -> dict[str, Any]:
    """Complete valid NATIVEAPP_TELEMETRY request payload."""
    tvid = TVID_1
    return {
        "TvEvent": {
            "tvid": tvid,
            "client": "smartcast",
            "h": _make_hmac(tvid),
            "EventType": "NATIVEAPP_TELEMETRY",
            "timestamp": 1709568000000,
        },
        "EventData": {
            "Timestamp": 1709568000000,
            "Namespace": "com.vizio.app",
            "AppId": "com.vizio.netflix",
            "action": "launch",
        },
    }


@pytest.fixture()
def sample_heartbeat_payload() -> dict[str, Any]:
    """Complete valid Heartbeat request (ACR_TUNER_DATA with Heartbeat key)."""
    tvid = TVID_2
    return {
        "TvEvent": {
            "tvid": tvid,
            "client": "smartcast",
            "h": _make_hmac(tvid),
            "EventType": "ACR_TUNER_DATA",
            "timestamp": 1709571600000,
            "appId": "com.vizio.smartcast",
            "Namespace": "vizio.acr",
        },
        "EventData": {
            "Heartbeat": {
                "channelData": {
                    "majorId": 501,
                    "minorId": 1,
                    "channelId": "10501",
                    "channelName": "ESPN",
                },
            },
        },
    }


# ── Mock services ────────────────────────────────────────────────────────


@pytest.fixture()
def mock_kafka_producer() -> AsyncMock:
    """Mock KafkaProducerService — send always succeeds, health OK."""
    kafka = AsyncMock()
    kafka.send = AsyncMock()
    kafka.health_check = AsyncMock(return_value=True)
    kafka.close = AsyncMock()
    kafka.connect = AsyncMock()
    return kafka


@pytest.fixture()
def mock_rds_client() -> AsyncMock:
    """Mock RdsClient returning test blacklisted channels."""
    rds = AsyncMock()
    rds.fetch_blacklisted_channel_ids = AsyncMock(return_value=["10501", "99999"])
    rds.health_check = AsyncMock(return_value=True)
    rds.connect = AsyncMock()
    rds.close = AsyncMock()
    rds.pool_size = 10
    rds.pool_free = 8
    return rds


@pytest.fixture()
def mock_redis_client() -> AsyncMock:
    """Mock Redis client with blacklisted channels as a set."""
    redis = AsyncMock()
    redis.smembers = AsyncMock(return_value={b"10501", b"99999"})
    redis.sismember = AsyncMock(side_effect=lambda key, val: val in {"10501", "99999"})
    redis.ping = AsyncMock(return_value=True)
    redis.delete = AsyncMock()
    redis.pipeline = MagicMock()

    pipe = AsyncMock()
    pipe.delete = AsyncMock()
    pipe.sadd = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.execute = AsyncMock()
    redis.pipeline.return_value = pipe

    redis.aclose = AsyncMock()
    return redis


@pytest.fixture()
def mock_cache_service(mock_redis_client: AsyncMock, mock_rds_client: AsyncMock) -> AsyncMock:
    """Mock BlacklistCacheService with realistic behaviour."""
    cache = AsyncMock()
    cache.is_blacklisted = AsyncMock(side_effect=lambda cid: cid in {"10501", "99999"})
    cache.get_blacklisted_channels = AsyncMock(return_value={"10501", "99999"})
    cache.refresh_cache = AsyncMock(return_value={"10501", "99999"})
    cache.flush_cache = AsyncMock()
    cache.seconds_since_refresh = 42.0
    return cache


# ── App client ───────────────────────────────────────────────────────────


def _build_test_app(
    settings: Settings,
    mock_kafka: AsyncMock,
    mock_rds: AsyncMock,
    mock_redis: AsyncMock,
    mock_cache: AsyncMock,
) -> Any:
    """Create a FastAPI app with all services mocked via direct state injection.

    httpx.ASGITransport does not send ASGI lifespan events, so we
    bypass the lifespan context entirely and set ``app.state`` directly.
    We use a no-op lifespan to prevent the real one from trying to
    connect to Kafka/RDS/Redis.
    """
    import time as _time
    from contextlib import asynccontextmanager as _acm

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    from tvevents import __version__
    from tvevents.api.health import router as health_router
    from tvevents.api.routes import router as events_router
    from tvevents.domain.validation import (
        TvEventsCatchallException,
        TvEventsDefaultException,
        TvEventsInvalidPayloadError,
        TvEventsMissingRequiredParamError,
        TvEventsSecurityValidationError,
    )
    from tvevents.main import _make_error_response
    from tvevents.middleware.metrics import MetricsMiddleware
    from tvevents.ops.diagnostics import router as diagnostics_router
    from tvevents.ops.remediation import router as remediation_router

    @_acm
    async def _noop_lifespan(app_inner: FastAPI) -> AsyncGeneratorType[None, None]:
        yield

    app = FastAPI(
        title="rebuilder-evergreen-tvevents-test",
        version=__version__,
        lifespan=_noop_lifespan,
    )

    # Inject mock services directly onto app.state
    app.state.settings = settings
    app.state.start_time = _time.monotonic()
    app.state.drain_mode = False
    app.state.circuits = {"kafka": "closed", "rds": "closed", "redis": "closed"}
    app.state.kafka = mock_kafka
    app.state.rds = mock_rds
    app.state.redis = mock_redis
    app.state.cache = mock_cache

    app.add_middleware(MetricsMiddleware)
    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(diagnostics_router)
    app.include_router(remediation_router)

    # Exception handlers (same as create_app)
    @app.exception_handler(TvEventsMissingRequiredParamError)
    async def _missing_param(
        request: Request, exc: TvEventsMissingRequiredParamError
    ) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsSecurityValidationError)
    async def _security_error(
        request: Request, exc: TvEventsSecurityValidationError
    ) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsInvalidPayloadError)
    async def _invalid_payload(request: Request, exc: TvEventsInvalidPayloadError) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsCatchallException)
    async def _catchall(request: Request, exc: TvEventsCatchallException) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(TvEventsDefaultException)
    async def _default(request: Request, exc: TvEventsDefaultException) -> JSONResponse:
        return _make_error_response(request, exc, exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return _make_error_response(request, exc, 500)

    @app.middleware("http")
    async def drain_guard(request: Request, call_next: Any) -> Any:
        if getattr(request.app.state, "drain_mode", False) and not (
            request.url.path.startswith("/ops")
            or request.url.path == "/health"
            or request.url.path == "/docs"
            or request.url.path == "/openapi.json"
        ):
            return JSONResponse(
                status_code=503,
                content={"error": "ServiceDraining", "message": "Service is draining"},
            )
        return await call_next(request)

    return app


@pytest_asyncio.fixture()
async def app_client(
    settings: Settings,
    mock_kafka_producer: AsyncMock,
    mock_rds_client: AsyncMock,
    mock_redis_client: AsyncMock,
    mock_cache_service: AsyncMock,
) -> AsyncClient:
    """httpx.AsyncClient wired to the FastAPI app with all services mocked."""
    app = _build_test_app(
        settings, mock_kafka_producer, mock_rds_client, mock_redis_client, mock_cache_service
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
