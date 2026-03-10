"""Event type dispatch and validation — ported from legacy app/event_type.py."""


from abc import abstractmethod
import logging
from typing import Any

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from tvevents.domain.transform import flatten_request_json, get_payload_namespace
from tvevents.domain.validation import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
    timestamp_check,
    unix_time_to_ms,
    verify_required_params,
)

logger = logging.getLogger(__name__)


class EventType:
    """Base class for event type validation and output generation."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.event_type: str = payload["TvEvent"]["EventType"]
        self.tvid: str = payload["TvEvent"]["tvid"]
        self.event_data_params: dict[str, Any] = payload["EventData"]
        self.namespace: str | None = None
        self.appid: str | None = None

    @abstractmethod
    def validate_event_type_payload(self) -> bool:
        """Ensure required fields for event_type are present."""
        ...

    @abstractmethod
    def generate_event_data_output_json(self) -> dict[str, Any]:
        """Generate output json for event_type EventData."""
        ...


class NativeAppTelemetryEventType(EventType):
    """NATIVEAPP_TELEMETRY event type handler."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)
        self.namespace = get_payload_namespace(self.event_data_params)
        self.appid = self.event_data_params.get("AppId")

    def validate_event_type_payload(self) -> bool:
        req_fields = ["Timestamp"]
        verify_required_params(self.event_data_params, req_fields)
        timestamp_check(self.event_data_params["Timestamp"], self.tvid)
        return True

    def generate_event_data_output_json(self) -> dict[str, Any]:
        event_data_json = self.payload["EventData"]
        event_data_output: dict[str, Any] = {}
        event_data_output.update(
            flatten_request_json(event_data_json, ignore_keys="Timestamp")
        )
        event_data_output["eventdata_timestamp"] = event_data_json["Timestamp"]
        return event_data_output


class AcrTunerDataEventType(EventType):
    """ACR_TUNER_DATA event type handler."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)
        self.namespace = get_payload_namespace(self.payload["TvEvent"])
        self.appid = self.payload["TvEvent"].get("appId")

    def validate_event_type_payload(self) -> bool:
        is_heartbeat_event = "Heartbeat" in self.event_data_params
        if is_heartbeat_event and self._validate_heartbeat_event():
            ed_params = self.event_data_params["Heartbeat"]
        else:
            optional_params = ["channelData", "programData"]
            if not any(param in self.event_data_params for param in optional_params):
                msg = (
                    f"Missing Required Param: {optional_params} "
                    f"tvid={self.tvid} EventType={self.event_type}"
                )
                raise TvEventsMissingRequiredParamError(msg)
            ed_params = self.event_data_params

        if "channelData" in ed_params:
            req_channel_data = ["majorId", "minorId"]
            verify_required_params(ed_params["channelData"], req_channel_data)

        if "resolution" in ed_params:
            req_resolution = ["vRes", "hRes"]
            verify_required_params(ed_params["resolution"], req_resolution)

        return True

    def _validate_heartbeat_event(self) -> bool:
        """Validate heartbeat event structure."""
        other_params = ["channelData", "programData"]
        if any(param in self.event_data_params for param in other_params):
            msg = (
                f"Heartbeat cannot be sent with channel/program Data: "
                f"tvid={self.tvid} EventType={self.event_type}"
            )
            raise TvEventsInvalidPayloadError(msg)

        hb_params = self.event_data_params["Heartbeat"]
        if not any(param in hb_params for param in other_params):
            msg = (
                f"Required Heartbeat Param: {other_params} missing: "
                f"tvid={self.tvid} EventType={self.event_type}"
            )
            raise TvEventsMissingRequiredParamError(msg)

        return True

    def generate_event_data_output_json(self) -> dict[str, Any]:
        event_data_json = self.payload["EventData"]
        event_data_output: dict[str, Any] = {}
        event_data_output.update(flatten_request_json(event_data_json))

        if "programdata_starttime" in event_data_output and timestamp_check(
            event_data_output["programdata_starttime"], self.tvid, is_ms=False
        ):
            event_data_output["programdata_starttime"] = unix_time_to_ms(
                event_data_output["programdata_starttime"]
            )

        if event_data_json.get("Heartbeat"):
            logger.debug("Heartbeat event received for tvid=%s", self.tvid)
            event_data_output["eventtype"] = "Heartbeat"

        return event_data_output


class PlatformTelemetryEventType(EventType):
    """PLATFORM_TELEMETRY event type handler."""

    panel_data_schema: dict[str, Any] = {
        "required": ["Timestamp", "PanelState", "WakeupReason"],
        "type": "object",
        "properties": {
            "Timestamp": {"type": "number"},
            "PanelState": {"type": "string", "pattern": "^(ON|OFF|on|off|On|Off)$"},
            "WakeupReason": {"type": "number", "minimum": 0, "maximum": 128},
        },
    }

    platform_telemetry_schema: dict[str, Any] = {
        "required": ["PanelData"],
        "type": "object",
        "properties": {"PanelData": panel_data_schema},
    }

    def validate_event_type_payload(self) -> bool:
        try:
            validate(
                instance=self.event_data_params,
                schema=self.platform_telemetry_schema,
            )
            self._validate_panel_data()
        except ValidationError as e:
            if e.validator == "required":
                msg = (
                    f"Missing Required Param: {e.message.split()[0]} "
                    f"tvid={self.tvid} EventType={self.event_type}"
                )
                raise TvEventsMissingRequiredParamError(msg) from e
            else:
                field = e.path.pop() if e.path else "unknown"
                msg = (
                    f"Invalid Payload: tvid={self.tvid} "
                    f"EventType: {self.event_type}, {field}-{e.message}"
                )
                raise TvEventsInvalidPayloadError(msg) from e
        return True

    def _validate_panel_data(self) -> bool:
        """Validate PanelData sub-schema and timestamp."""
        pd_params = self.event_data_params["PanelData"]
        validate(instance=pd_params, schema=self.panel_data_schema)
        timestamp_check(pd_params["Timestamp"], self.tvid)
        return True

    def generate_event_data_output_json(self) -> dict[str, Any]:
        event_data_json = self.payload["EventData"]
        event_data_output: dict[str, Any] = {}
        event_data_output.update(flatten_request_json(event_data_json))
        event_data_output["paneldata_panelstate"] = event_data_output[
            "paneldata_panelstate"
        ].upper()
        return event_data_output


EVENT_TYPE_MAP: dict[str, type[EventType]] = {
    "NATIVEAPP_TELEMETRY": NativeAppTelemetryEventType,
    "ACR_TUNER_DATA": AcrTunerDataEventType,
    "PLATFORM_TELEMETRY": PlatformTelemetryEventType,
}
