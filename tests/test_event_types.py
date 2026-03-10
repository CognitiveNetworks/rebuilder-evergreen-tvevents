"""Tests for tvevents.domain.event_types module."""

import pytest

from tests.conftest import make_valid_payload
from tvevents.domain.validation import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
)


class TestAcrTunerDataEventType:
    """Tests for AcrTunerDataEventType."""

    def test_valid_channel_data(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(event_type="ACR_TUNER_DATA")
        et = AcrTunerDataEventType(payload)
        assert et.validate_event_type_payload() is True

    def test_missing_channel_and_program_data(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(
            event_type="ACR_TUNER_DATA",
            event_data={"someField": "value"},
        )
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError):
            et.validate_event_type_payload()

    def test_valid_heartbeat(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(
            event_type="ACR_TUNER_DATA",
            event_data={
                "Heartbeat": {
                    "channelData": {"channelid": "123", "majorId": 1, "minorId": 0}
                }
            },
        )
        et = AcrTunerDataEventType(payload)
        assert et.validate_event_type_payload() is True

    def test_heartbeat_with_channel_data_raises(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(
            event_type="ACR_TUNER_DATA",
            event_data={
                "Heartbeat": {"channelData": {"channelid": "123", "majorId": 1, "minorId": 0}},
                "channelData": {"channelid": "456", "majorId": 2, "minorId": 0},
            },
        )
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError, match="Heartbeat cannot be sent"):
            et.validate_event_type_payload()

    def test_heartbeat_missing_required_params(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(
            event_type="ACR_TUNER_DATA",
            event_data={"Heartbeat": {"someField": "value"}},
        )
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="Required Heartbeat Param"):
            et.validate_event_type_payload()

    def test_generate_output_converts_starttime_to_ms(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(event_type="ACR_TUNER_DATA")
        et = AcrTunerDataEventType(payload)
        output = et.generate_event_data_output_json()
        assert output["programdata_starttime"] == 1700000000 * 1000

    def test_generate_output_heartbeat_sets_eventtype(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(
            event_type="ACR_TUNER_DATA",
            event_data={
                "Heartbeat": {
                    "channelData": {"channelid": "123", "majorId": 1, "minorId": 0}
                }
            },
        )
        et = AcrTunerDataEventType(payload)
        output = et.generate_event_data_output_json()
        assert output["eventtype"] == "Heartbeat"

    def test_namespace_from_tvevent(self) -> None:
        from tvevents.domain.event_types import AcrTunerDataEventType

        payload = make_valid_payload(event_type="ACR_TUNER_DATA")
        payload["TvEvent"]["Namespace"] = "com.vizio.acr"
        et = AcrTunerDataEventType(payload)
        assert et.namespace == "com.vizio.acr"


class TestNativeAppTelemetryEventType:
    """Tests for NativeAppTelemetryEventType."""

    def test_valid_payload(self) -> None:
        from tvevents.domain.event_types import NativeAppTelemetryEventType

        payload = make_valid_payload(
            event_type="NATIVEAPP_TELEMETRY",
            event_data={
                "Timestamp": 1700000000000,
                "Namespace": "com.vizio.app",
                "AppId": "APP001",
            },
        )
        et = NativeAppTelemetryEventType(payload)
        assert et.validate_event_type_payload() is True
        assert et.namespace == "com.vizio.app"
        assert et.appid == "APP001"

    def test_missing_timestamp_raises(self) -> None:
        from tvevents.domain.event_types import NativeAppTelemetryEventType

        payload = make_valid_payload(
            event_type="NATIVEAPP_TELEMETRY",
            event_data={"Namespace": "com.vizio.app"},
        )
        et = NativeAppTelemetryEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="Timestamp"):
            et.validate_event_type_payload()

    def test_generate_output(self) -> None:
        from tvevents.domain.event_types import NativeAppTelemetryEventType

        payload = make_valid_payload(
            event_type="NATIVEAPP_TELEMETRY",
            event_data={
                "Timestamp": 1700000000000,
                "Namespace": "com.vizio.app",
                "AppId": "APP001",
                "SomeField": "value",
            },
        )
        et = NativeAppTelemetryEventType(payload)
        output = et.generate_event_data_output_json()
        assert output["eventdata_timestamp"] == 1700000000000
        assert output["somefield"] == "value"
        assert "timestamp" not in output


class TestPlatformTelemetryEventType:
    """Tests for PlatformTelemetryEventType."""

    def test_valid_payload(self) -> None:
        from tvevents.domain.event_types import PlatformTelemetryEventType

        payload = make_valid_payload(
            event_type="PLATFORM_TELEMETRY",
            event_data={
                "PanelData": {
                    "Timestamp": 1700000000000,
                    "PanelState": "ON",
                    "WakeupReason": 1,
                }
            },
        )
        et = PlatformTelemetryEventType(payload)
        assert et.validate_event_type_payload() is True

    def test_missing_panel_data_raises(self) -> None:
        from tvevents.domain.event_types import PlatformTelemetryEventType

        payload = make_valid_payload(
            event_type="PLATFORM_TELEMETRY",
            event_data={"SomeField": "value"},
        )
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError):
            et.validate_event_type_payload()

    def test_invalid_panel_state_raises(self) -> None:
        from tvevents.domain.event_types import PlatformTelemetryEventType

        payload = make_valid_payload(
            event_type="PLATFORM_TELEMETRY",
            event_data={
                "PanelData": {
                    "Timestamp": 1700000000000,
                    "PanelState": "INVALID",
                    "WakeupReason": 1,
                }
            },
        )
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_generate_output_uppercases_panel_state(self) -> None:
        from tvevents.domain.event_types import PlatformTelemetryEventType

        payload = make_valid_payload(
            event_type="PLATFORM_TELEMETRY",
            event_data={
                "PanelData": {
                    "Timestamp": 1700000000000,
                    "PanelState": "on",
                    "WakeupReason": 1,
                }
            },
        )
        et = PlatformTelemetryEventType(payload)
        output = et.generate_event_data_output_json()
        assert output["paneldata_panelstate"] == "ON"

    def test_wakeup_reason_out_of_range(self) -> None:
        from tvevents.domain.event_types import PlatformTelemetryEventType

        payload = make_valid_payload(
            event_type="PLATFORM_TELEMETRY",
            event_data={
                "PanelData": {
                    "Timestamp": 1700000000000,
                    "PanelState": "ON",
                    "WakeupReason": 200,
                }
            },
        )
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()


class TestEventTypeMap:
    """Tests for EVENT_TYPE_MAP dispatch."""

    def test_all_event_types_registered(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP

        assert "ACR_TUNER_DATA" in EVENT_TYPE_MAP
        assert "NATIVEAPP_TELEMETRY" in EVENT_TYPE_MAP
        assert "PLATFORM_TELEMETRY" in EVENT_TYPE_MAP

    def test_unknown_event_type_not_in_map(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP

        assert "UNKNOWN_TYPE" not in EVENT_TYPE_MAP
