"""Shared test fixtures for tvevents-k8s."""

import hashlib
import os
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required environment variables for all tests."""
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("T1_SALT", "test-salt")
    monkeypatch.setenv("RDS_HOST", "localhost")
    monkeypatch.setenv("RDS_DB", "tvevents_test")
    monkeypatch.setenv("RDS_USER", "postgres")
    monkeypatch.setenv("RDS_PASS", "postgres")
    monkeypatch.setenv("RDS_PORT", "5432")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    monkeypatch.setenv("KAFKA_TOPIC_EVERGREEN", "test-evergreen")
    monkeypatch.setenv("KAFKA_TOPIC_LEGACY", "test-legacy")
    monkeypatch.setenv("KAFKA_TOPIC_DEBUG_EVERGREEN", "test-debug-evergreen")
    monkeypatch.setenv("KAFKA_TOPIC_DEBUG_LEGACY", "test-debug-legacy")
    monkeypatch.setenv("SEND_EVERGREEN", "true")
    monkeypatch.setenv("SEND_LEGACY", "true")
    monkeypatch.setenv("TVEVENTS_DEBUG", "false")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", "/tmp/.test_blacklist_cache")

    # Reset singletons between tests
    import tvevents.config as cfg
    cfg._settings = None
    import tvevents.deps as deps_mod
    deps_mod.reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a FastAPI test client."""
    import tvevents.deps as deps_mod
    deps_mod.reset()

    from tvevents.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def salt() -> str:
    """Return the test T1_SALT value."""
    return "test-salt"


def make_valid_hash(tvid: str, salt: str = "test-salt") -> str:
    """Generate a valid HMAC hash for testing (MD5 for us-east-1)."""
    return hashlib.md5(f"{tvid}{salt}".encode("utf-8")).hexdigest()


def make_valid_payload(
    tvid: str = "test-tvid-001",
    event_type: str = "ACR_TUNER_DATA",
    salt: str = "test-salt",
    event_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a valid TV event payload for testing."""
    h = make_valid_hash(tvid, salt)
    if event_data is None:
        event_data = {
            "channelData": {
                "channelid": "99999",
                "channelname": "TestChannel",
                "majorId": 1,
                "minorId": 0,
            },
            "programData": {
                "programid": "PROG001",
                "starttime": 1700000000,
            },
        }
    return {
        "TvEvent": {
            "tvid": tvid,
            "client": "test-client",
            "h": h,
            "EventType": event_type,
            "timestamp": 1700000000000,
        },
        "EventData": event_data,
    }
