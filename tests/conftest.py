"""Shared fixtures for evergreen-tvevents tests."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure OTEL is disabled in tests
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("SERVICE_NAME", "evergreen-tvevents")
os.environ.setdefault("T1_SALT", "test-salt-value")
os.environ.setdefault("ZOO", "test")
os.environ.setdefault("SEND_EVERGREEN", "true")
os.environ.setdefault("SEND_LEGACY", "false")
os.environ.setdefault("TVEVENTS_DEBUG", "false")
os.environ.setdefault("KAFKA_TOPIC_EVERGREEN", "evergreen-tvevents")
os.environ.setdefault("KAFKA_TOPIC_LEGACY", "legacy-tvevents")
os.environ.setdefault("KAFKA_TOPIC_EVERGREEN_DEBUG", "evergreen-tvevents-debug")
os.environ.setdefault("KAFKA_TOPIC_LEGACY_DEBUG", "legacy-tvevents-debug")
os.environ.setdefault(
    "BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH",
    "/tmp/.test_blacklist_cache",  # noqa: S108
)

# Mock external modules before any app imports
mock_rds = MagicMock()
mock_rds.execute_query = MagicMock(return_value=[])
sys.modules["rds_module"] = mock_rds

mock_kafka = MagicMock()
mock_kafka.send_message = MagicMock()
mock_kafka.health_check = MagicMock()
sys.modules["kafka_module"] = mock_kafka

# Mock cnlib modules
mock_cnlib = MagicMock()
mock_cnlib_cnlib = MagicMock()
mock_token_hash = MagicMock()
mock_token_hash.security_hash_match = MagicMock(return_value=True)
mock_cnlib_cnlib.token_hash = mock_token_hash
mock_cnlib.cnlib = mock_cnlib_cnlib

mock_cnlib_log = MagicMock()
mock_cnlib_log.Log = MagicMock()
mock_cnlib_log.Log.return_value.LOGGER = MagicMock()

sys.modules["cnlib"] = mock_cnlib
sys.modules["cnlib.cnlib"] = mock_cnlib_cnlib
sys.modules["cnlib.cnlib.token_hash"] = mock_token_hash
sys.modules["cnlib.log"] = mock_cnlib_log


@pytest.fixture
def mock_rds_module():
    """Provide the mocked rds_module."""
    mock_rds.execute_query.reset_mock()
    mock_rds.execute_query.return_value = []
    mock_rds.execute_query.side_effect = None
    return mock_rds


@pytest.fixture
def mock_kafka_module():
    """Provide the mocked kafka_module."""
    mock_kafka.send_message.reset_mock()
    mock_kafka.send_message.side_effect = None
    mock_kafka.health_check.reset_mock()
    mock_kafka.health_check.side_effect = None
    return mock_kafka


@pytest.fixture
def mock_security_hash():
    """Provide the mocked security_hash_match."""
    mock_token_hash.security_hash_match.reset_mock()
    mock_token_hash.security_hash_match.return_value = True
    return mock_token_hash


@pytest.fixture
def sample_nativeapp_payload():
    """Valid NativeAppTelemetry payload from a SmartCast TV device."""
    return {
        "TvEvent": {
            "tvid": "VZR2023A7F4E9B01",
            "client": "smartcast",
            "h": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            "EventType": "NATIVEAPP_TELEMETRY",
            "timestamp": "1700000000000",
        },
        "EventData": {
            "Timestamp": 1700000000000,
            "AppId": "com.vizio.smartcast.gallery",
            "Namespace": "smartcast_apps",
            "Data": {"key": "value"},
        },
    }


@pytest.fixture
def sample_acr_payload():
    """Valid AcrTunerData payload from an ACR-enabled SmartCast device."""
    return {
        "TvEvent": {
            "tvid": "VZR2024B3D8C2E07",
            "client": "smartcast",
            "h": "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3",
            "EventType": "ACR_TUNER_DATA",
            "timestamp": "1700000000000",
            "Namespace": "acr_content_recognition",
            "appId": "com.vizio.acr.tuner",
        },
        "EventData": {
            "channelNum": 206,
            "channelName": "ESPN",
            "channelId": "ch-espn-206",
            "programId": "prog-cfb-20231114",
            "channelData": {"majorId": 206, "minorId": 1},
            "programData": {
                "programdata_starttime": "1700000000",
            },
            "resolution": {"vRes": 1920, "hRes": 1080},
        },
    }


@pytest.fixture
def sample_platform_payload():
    """Valid PlatformTelemetry payload from a SmartCast TV panel state change."""
    return {
        "TvEvent": {
            "tvid": "VZR2023F1A9D5C12",
            "client": "smartcast",
            "h": "d4c3b2a1e5f6d4c3b2a1e5f6d4c3b2a1",
            "EventType": "PLATFORM_TELEMETRY",
            "timestamp": "1700000000000",
        },
        "EventData": {
            "PanelData": {
                "PanelState": "ON",
                "WakeupReason": 1,
                "Timestamp": 1700000000,
            },
        },
    }


@pytest.fixture
def sample_url_params():
    """Valid URL params matching a NativeAppTelemetry request."""
    return {
        "tvid": "VZR2023A7F4E9B01",
        "client": "smartcast",
        "h": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "EventType": "NATIVEAPP_TELEMETRY",
        "timestamp": "1700000000000",
    }
