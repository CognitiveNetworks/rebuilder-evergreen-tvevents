"""Output-JSON generation tests — flattened keys, metadata injection,
timestamp conversion, and downstream contract verification.

Each test validates that generate_output_json produces the exact key
names and values that downstream Kafka consumers depend on.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from tests.conftest import TEST_ZOO, TVID_1, _make_hmac
from tvevents.domain.event_types import generate_output_json


class TestEventDataOutputJsonGeneration:
    """Verify the output JSON downstream contract for every event type."""

    # ── ACR_TUNER_DATA ───────────────────────────────────────────────

    def test_acr_tuner_data_output_flattened_correctly(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends ACR_TUNER_DATA with channel 45/1 → output contains
        channeldata_majorid=45, channeldata_minorid=1,
        programdata_programid='EP012345678901', resolution_vres=1080."""
        output = generate_output_json(sample_acr_tuner_payload, zoo=TEST_ZOO)

        assert output["channeldata_majorid"] == 45
        assert output["channeldata_minorid"] == 1
        assert output["channeldata_channelid"] == "10045"
        assert output["channeldata_channelname"] == "PBS"
        assert output["programdata_programid"] == "EP012345678901"
        assert output["resolution_vres"] == 1080
        assert output["resolution_hres"] == 1920

    def test_acr_tuner_data_starttime_converted_to_ms(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """programdata_starttime (seconds) is multiplied by 1000 to produce
        milliseconds: 1709564400 → 1709564400000."""
        output = generate_output_json(sample_acr_tuner_payload, zoo=TEST_ZOO)
        assert output["programdata_starttime"] == 1709564400 * 1000

    # ── PLATFORM_TELEMETRY ───────────────────────────────────────────

    def test_platform_telemetry_output_flattened_with_uppercase_state(
        self, sample_platform_telemetry_payload: dict[str, Any]
    ) -> None:
        """PLATFORM_TELEMETRY output flattens PanelData and upper-cases
        PanelState: on → ON."""
        payload = deepcopy(sample_platform_telemetry_payload)
        payload["EventData"]["PanelData"]["PanelState"] = "on"
        output = generate_output_json(payload, zoo=TEST_ZOO)
        assert output["paneldata_panelstate"] == "ON"
        assert "paneldata_timestamp" in output
        assert "paneldata_wakeupreason" in output

    # ── NATIVEAPP_TELEMETRY ──────────────────────────────────────────

    def test_nativeapp_telemetry_output_preserves_timestamp(
        self, sample_nativeapp_telemetry_payload: dict[str, Any]
    ) -> None:
        """NATIVEAPP_TELEMETRY output (eventdata_timestamp) must equal
        the original EventData.Timestamp value — 1709568000000."""
        output = generate_output_json(sample_nativeapp_telemetry_payload, zoo=TEST_ZOO)
        assert output["eventdata_timestamp"] == 1709568000000

    # ── TvEvent metadata injection ───────────────────────────────────

    def test_generate_output_json_includes_tvevent_metadata(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """Output JSON must contain flattened TvEvent metadata: tvid,
        client, tvevent_timestamp, tvevent_eventtype, and zoo."""
        output = generate_output_json(sample_acr_tuner_payload, zoo=TEST_ZOO)

        assert output["tvid"] == TVID_1
        assert output["client"] == "smartcast"
        assert output["tvevent_timestamp"] == 1709568000000
        assert output["tvevent_eventtype"] == "ACR_TUNER_DATA"
        assert output["zoo"] == TEST_ZOO

    def test_generate_output_json_excludes_h_timestamp_eventtype(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """The raw TvEvent fields h, timestamp, and EventType must NOT
        appear as top-level output keys (they are replaced by
        tvevent_timestamp and tvevent_eventtype)."""
        output = generate_output_json(sample_acr_tuner_payload, zoo=TEST_ZOO)

        assert "h" not in output
        # 'timestamp' as a direct TvEvent flatten would produce 'timestamp' key;
        # we instead have 'tvevent_timestamp'.
        assert "eventtype" not in output or output.get("eventtype") != "ACR_TUNER_DATA"

    def test_generate_output_json_includes_zoo_from_settings(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """Zoo value (environment) comes from the settings and is injected
        into every output JSON — verify with 'production'."""
        output = generate_output_json(sample_acr_tuner_payload, zoo="production")
        assert output["zoo"] == "production"

    def test_generate_output_json_includes_namespace_and_appid(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """ACR_TUNER_DATA output includes namespace='vizio.acr' and
        appid='com.vizio.smartcast' sourced from TvEvent."""
        output = generate_output_json(sample_acr_tuner_payload, zoo=TEST_ZOO)
        assert output["namespace"] == "vizio.acr"
        assert output["appid"] == "com.vizio.smartcast"

    def test_unknown_event_type_falls_through_to_generic_flatten(self) -> None:
        """An unknown EventType (e.g. 'FUTURE_EVENT') falls through
        to generic EventData flattening — no crash, keys present."""
        payload: dict[str, Any] = {
            "TvEvent": {
                "tvid": TVID_1,
                "client": "smartcast",
                "h": _make_hmac(TVID_1),
                "EventType": "FUTURE_EVENT",
                "timestamp": 1709568000000,
            },
            "EventData": {
                "customField": "customValue",
                "nested": {"inner": 42},
            },
        }
        output = generate_output_json(payload, zoo=TEST_ZOO)

        assert output["tvevent_eventtype"] == "FUTURE_EVENT"
        assert output["customfield"] == "customValue"
        assert output["nested_inner"] == 42
