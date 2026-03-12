"""Tests for app.event_type module."""

import pytest

from app.event_type import (
    AcrTunerDataEventType,
    NativeAppTelemetryEventType,
    PlatformTelemetryEventType,
    event_type_map,
    flatten_request_json,
)
from app.exceptions import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
)


class TestEventTypeMap:
    def test_nativeapp_in_map(self):
        assert "NATIVEAPP_TELEMETRY" in event_type_map

    def test_acr_in_map(self):
        assert "ACR_TUNER_DATA" in event_type_map

    def test_platform_in_map(self):
        assert "PLATFORM_TELEMETRY" in event_type_map

    def test_map_has_three_entries(self):
        assert len(event_type_map) == 3


class TestFlattenRequestJson:
    def test_flat_dict(self):
        result = flatten_request_json({"key1": "val1", "key2": "val2"}, "pre")
        assert result == {"pre_key1": "val1", "pre_key2": "val2"}

    def test_nested_dict(self):
        result = flatten_request_json({"outer": {"inner": "val"}}, "pre")
        assert result == {"outer_inner": "val"}

    def test_ignore_keys(self):
        result = flatten_request_json(
            {"keep": "yes", "drop": "no"}, "pre", ignore_keys=["drop"]
        )
        assert result == {"pre_keep": "yes"}

    def test_keys_lowercased(self):
        result = flatten_request_json({"CamelKey": "value"}, "pre")
        assert "pre_camelkey" in result


class TestNativeAppTelemetryEventType:
    def test_valid_payload(self, sample_nativeapp_payload):
        et = NativeAppTelemetryEventType(sample_nativeapp_payload)
        et.validate_event_type_payload()

    def test_missing_timestamp_passes(self):
        payload = {
            "TvEvent": {"tvid": "VZR2023A7F4E9B01", "EventType": "NATIVEAPP_TELEMETRY"},
            "EventData": {"AppId": "com.vizio.smartcast.gallery", "Namespace": "ns"},
        }
        et = NativeAppTelemetryEventType(payload)
        et.validate_event_type_payload()

    def test_invalid_timestamp_raises(self):
        payload = {
            "TvEvent": {"tvid": "VZR2023A7F4E9B01", "EventType": "NATIVEAPP_TELEMETRY"},
            "EventData": {"Timestamp": "not_a_number", "Namespace": "ns"},
        }
        et = NativeAppTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_namespace_from_event_data(self, sample_nativeapp_payload):
        et = NativeAppTelemetryEventType(sample_nativeapp_payload)
        assert et.namespace == "smartcast_apps"

    def test_generate_output(self, sample_nativeapp_payload):
        et = NativeAppTelemetryEventType(sample_nativeapp_payload)
        result = et.generate_event_data_output_json()
        assert isinstance(result, dict)


class TestAcrTunerDataEventType:
    def test_valid_payload(self, sample_acr_payload):
        et = AcrTunerDataEventType(sample_acr_payload)
        et.validate_event_type_payload()

    def test_heartbeat_with_channel_data_raises(self):
        payload = {
            "TvEvent": {"tvid": "VZR2024B3D8C2E07", "EventType": "ACR_TUNER_DATA"},
            "EventData": {
                "Heartbeat": {"channelData": {}},
                "channelData": {"majorId": 1, "minorId": 2},
            },
        }
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError, match="[Hh]eartbeat"):
            et.validate_event_type_payload()

    def test_missing_channel_data_raises(self):
        payload = {
            "TvEvent": {"tvid": "VZR2024B3D8C2E07", "EventType": "ACR_TUNER_DATA"},
            "EventData": {},
        }
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError):
            et.validate_event_type_payload()

    def test_namespace_from_tvevent(self, sample_acr_payload):
        et = AcrTunerDataEventType(sample_acr_payload)
        assert et.namespace == "acr_content_recognition"

    def test_generate_output(self, sample_acr_payload):
        et = AcrTunerDataEventType(sample_acr_payload)
        result = et.generate_event_data_output_json()
        assert isinstance(result, dict)


class TestPlatformTelemetryEventType:
    def test_valid_payload(self, sample_platform_payload):
        et = PlatformTelemetryEventType(sample_platform_payload)
        et.validate_event_type_payload()

    def test_invalid_panel_state_raises(self):
        payload = {
            "TvEvent": {"tvid": "VZR2023F1A9D5C12", "EventType": "PLATFORM_TELEMETRY"},
            "EventData": {
                "PanelData": {
                    "PanelState": "INVALID",
                    "WakeupReason": 1,
                    "Timestamp": 1700000000,
                },
            },
        }
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_invalid_wakeup_reason_raises(self):
        payload = {
            "TvEvent": {"tvid": "VZR2023F1A9D5C12", "EventType": "PLATFORM_TELEMETRY"},
            "EventData": {
                "PanelData": {
                    "PanelState": "ON",
                    "WakeupReason": 999,
                    "Timestamp": 1700000000,
                },
            },
        }
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_missing_panel_data_raises(self):
        payload = {
            "TvEvent": {"tvid": "VZR2023F1A9D5C12", "EventType": "PLATFORM_TELEMETRY"},
            "EventData": {},
        }
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError):
            et.validate_event_type_payload()

    def test_generate_output_uppercases_panelstate(self, sample_platform_payload):
        et = PlatformTelemetryEventType(sample_platform_payload)
        result = et.generate_event_data_output_json()
        assert isinstance(result, dict)
