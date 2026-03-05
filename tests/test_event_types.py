"""Event-type validation tests — ACR_TUNER_DATA, PLATFORM_TELEMETRY,
NATIVEAPP_TELEMETRY, and Heartbeat lifecycle.

Each class exercises the validate_event_type_payload method of the
corresponding EventType subclass using realistic Smart TV payloads.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from tvevents.domain.event_types import (
    AcrTunerDataEventType,
    NativeAppTelemetryEventType,
    PlatformTelemetryEventType,
)
from tvevents.domain.validation import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
)

# ═════════════════════════════════════════════════════════════════════════
# ACR_TUNER_DATA
# ═════════════════════════════════════════════════════════════════════════


class TestAcrTunerDataEventValidation:
    """Validate ACR_TUNER_DATA payloads — channel data, program data,
    resolution, and namespace / appId sourcing rules."""

    def test_acr_tuner_with_channel_and_program_data_valid(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with channelData majorId=45, minorId=1
        and programData — validation passes."""
        et = AcrTunerDataEventType(sample_acr_tuner_payload)
        assert et.validate_event_type_payload() is True

    def test_acr_tuner_missing_both_channel_and_program_data_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with neither channelData nor programData
        → TvEventsMissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["EventData"]["channelData"]
        del payload["EventData"]["programData"]
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="Missing Required Param"):
            et.validate_event_type_payload()

    def test_acr_tuner_channel_data_missing_major_id_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with channelData but no majorId
        → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["EventData"]["channelData"]["majorId"]
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="majorId"):
            et.validate_event_type_payload()

    def test_acr_tuner_channel_data_missing_minor_id_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with channelData but no minorId
        → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["EventData"]["channelData"]["minorId"]
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="minorId"):
            et.validate_event_type_payload()

    def test_acr_tuner_resolution_missing_vres_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with resolution missing vRes
        → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["EventData"]["resolution"]["vRes"]
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="vRes"):
            et.validate_event_type_payload()

    def test_acr_tuner_resolution_missing_hres_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with resolution missing hRes
        → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["EventData"]["resolution"]["hRes"]
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="hRes"):
            et.validate_event_type_payload()

    def test_acr_tuner_namespace_from_tvevent(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """ACR_TUNER_DATA derives namespace from the TvEvent envelope,
        not from EventData — vizio.acr expected."""
        et = AcrTunerDataEventType(sample_acr_tuner_payload)
        assert et.namespace == "vizio.acr"

    def test_acr_tuner_appid_from_tvevent(self, sample_acr_tuner_payload: dict[str, Any]) -> None:
        """ACR_TUNER_DATA's appId comes from TvEvent.appId field
        → 'com.vizio.smartcast'."""
        et = AcrTunerDataEventType(sample_acr_tuner_payload)
        assert et.appid == "com.vizio.smartcast"


# ═════════════════════════════════════════════════════════════════════════
# Heartbeat (sub-type of ACR_TUNER_DATA)
# ═════════════════════════════════════════════════════════════════════════


class TestHeartbeatEventLifecycle:
    """Validate Heartbeat event constraints — channel data must live inside
    the Heartbeat key, never at the EventData level."""

    def test_heartbeat_with_channel_data_inside_valid(
        self, sample_heartbeat_payload: dict[str, Any]
    ) -> None:
        """TV sends Heartbeat with channelData inside the Heartbeat object
        (majorId=501, minorId=1) — validation passes."""
        et = AcrTunerDataEventType(sample_heartbeat_payload)
        assert et.validate_event_type_payload() is True

    def test_heartbeat_with_channel_data_at_event_data_level_rejected(
        self, sample_heartbeat_payload: dict[str, Any]
    ) -> None:
        """TV sends Heartbeat + channelData at the same EventData level
        → TvEventsInvalidPayloadError (cannot coexist)."""
        payload = deepcopy(sample_heartbeat_payload)
        payload["EventData"]["channelData"] = {
            "majorId": 45,
            "minorId": 1,
            "channelId": "10045",
            "channelName": "PBS",
        }
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError, match="Heartbeat cannot be sent"):
            et.validate_event_type_payload()

    def test_heartbeat_missing_inner_data_rejected(
        self, sample_heartbeat_payload: dict[str, Any]
    ) -> None:
        """TV sends Heartbeat without channelData or programData inside
        the Heartbeat object → MissingRequiredParamError."""
        payload = deepcopy(sample_heartbeat_payload)
        payload["EventData"]["Heartbeat"] = {}  # empty
        et = AcrTunerDataEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="Required Heartbeat Param"):
            et.validate_event_type_payload()

    def test_heartbeat_event_sets_eventtype_field(
        self, sample_heartbeat_payload: dict[str, Any]
    ) -> None:
        """When a Heartbeat is processed, the output JSON must contain
        eventtype='Heartbeat' so downstream consumers distinguish it."""
        et = AcrTunerDataEventType(sample_heartbeat_payload)
        output = et.generate_event_data_output_json()
        assert output["eventtype"] == "Heartbeat"


# ═════════════════════════════════════════════════════════════════════════
# PLATFORM_TELEMETRY
# ═════════════════════════════════════════════════════════════════════════


class TestPlatformTelemetryEventValidation:
    """Validate PLATFORM_TELEMETRY payloads — PanelData schema with
    PanelState (ON/OFF), Timestamp, and WakeupReason constraints."""

    def test_platform_telemetry_with_valid_panel_data(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends PLATFORM_TELEMETRY with PanelState=ON, Timestamp,
        WakeupReason=0 — all validation passes."""
        et = PlatformTelemetryEventType(sample_platform_telemetry_payload)
        assert et.validate_event_type_payload() is True

    def test_platform_telemetry_panel_state_off_valid(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends PanelState=OFF → validation passes."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["PanelState"] = "OFF"
        et = PlatformTelemetryEventType(payload)
        assert et.validate_event_type_payload() is True

    def test_platform_telemetry_panel_state_lowercase_valid(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends PanelState=on (lowercase) → validation passes because
        the JSON schema allows ON|OFF|on|off|On|Off."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["PanelState"] = "on"
        et = PlatformTelemetryEventType(payload)
        assert et.validate_event_type_payload() is True

    def test_platform_telemetry_missing_panel_data_rejected(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends PLATFORM_TELEMETRY without PanelData key
        → MissingRequiredParamError."""
        payload = deepcopy(sample_platform_telemetry_payload)
        del payload["EventData"]["PanelData"]
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError):
            et.validate_event_type_payload()

    def test_platform_telemetry_invalid_panel_state_rejected(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends PanelState=STANDBY → TvEventsInvalidPayloadError
        because the schema only allows ON/OFF variants."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["PanelState"] = "STANDBY"
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_platform_telemetry_wakeup_reason_over_128_rejected(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends WakeupReason=200 → TvEventsInvalidPayloadError
        (schema maximum is 128)."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["WakeupReason"] = 200
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_platform_telemetry_wakeup_reason_negative_rejected(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends WakeupReason=-1 → TvEventsInvalidPayloadError
        (schema minimum is 0)."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["WakeupReason"] = -1
        et = PlatformTelemetryEventType(payload)
        with pytest.raises(TvEventsInvalidPayloadError):
            et.validate_event_type_payload()

    def test_platform_telemetry_panel_state_uppercased_in_output(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """Output JSON uppercases PanelState — on → ON — maintaining
        the downstream contract."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["PanelState"] = "on"
        et = PlatformTelemetryEventType(payload)
        output = et.generate_event_data_output_json()
        assert output["paneldata_panelstate"] == "ON"


# ═════════════════════════════════════════════════════════════════════════
# NATIVEAPP_TELEMETRY
# ═════════════════════════════════════════════════════════════════════════


class TestNativeAppTelemetryEventValidation:
    """Validate NATIVEAPP_TELEMETRY payloads — required Timestamp,
    namespace / appId sourcing from EventData."""

    def test_nativeapp_telemetry_with_valid_timestamp(
        self, sample_nativeapp_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends NATIVEAPP_TELEMETRY with Timestamp=1709568000000
        → validation passes."""
        et = NativeAppTelemetryEventType(sample_nativeapp_telemetry_payload)
        assert et.validate_event_type_payload() is True

    def test_nativeapp_telemetry_missing_timestamp_rejected(
        self, sample_nativeapp_telemetry_payload: dict[str, Any]
    ) -> None:
        """TV sends NATIVEAPP_TELEMETRY without Timestamp in EventData
        → MissingRequiredParamError."""
        payload = deepcopy(sample_nativeapp_telemetry_payload)
        del payload["EventData"]["Timestamp"]
        et = NativeAppTelemetryEventType(payload)
        with pytest.raises(TvEventsMissingRequiredParamError, match="Timestamp"):
            et.validate_event_type_payload()

    def test_nativeapp_telemetry_namespace_from_event_data(
        self, sample_nativeapp_telemetry_payload: dict[str, Any]
    ) -> None:
        """NATIVEAPP_TELEMETRY derives namespace from EventData.Namespace
        → 'com.vizio.app'."""
        et = NativeAppTelemetryEventType(sample_nativeapp_telemetry_payload)
        assert et.namespace == "com.vizio.app"

    def test_nativeapp_telemetry_appid_from_event_data(
        self, sample_nativeapp_telemetry_payload: dict[str, Any]
    ) -> None:
        """NATIVEAPP_TELEMETRY's appId comes from EventData.AppId
        → 'com.vizio.netflix'."""
        et = NativeAppTelemetryEventType(sample_nativeapp_telemetry_payload)
        assert et.appid == "com.vizio.netflix"

    def test_nativeapp_telemetry_output_preserves_eventdata_timestamp(
        self, sample_nativeapp_telemetry_payload: dict[str, Any]
    ) -> None:
        """The generated output JSON must contain 'eventdata_timestamp'
        equal to the original EventData.Timestamp value."""
        et = NativeAppTelemetryEventType(sample_nativeapp_telemetry_payload)
        output = et.generate_event_data_output_json()
        assert output["eventdata_timestamp"] == 1709568000000
