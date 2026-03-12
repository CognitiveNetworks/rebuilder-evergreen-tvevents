"""Event type classification and payload validation."""

from __future__ import annotations

from jsonschema import ValidationError, validate
from opentelemetry import trace

from app import configure_logging, meter
from app.exceptions import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
)

LOGGER = configure_logging()
tracer = trace.get_tracer(__name__)

VALIDATE_PAYLOAD_COUNTER = meter.create_counter(
    name="event.type.validate.count",
    description="Event type payload validation counter",
)
HEARTBEAT_COUNTER = meter.create_counter(
    name="event.type.heartbeat.count",
    description="Heartbeat event counter",
)
GENERATE_EVENT_DATA_OUTPUT_COUNTER = meter.create_counter(
    name="event.type.generate_output.count",
    description="Event data output generation counter",
)
VERIFY_PANEL_DATA_COUNTER = meter.create_counter(
    name="event.type.panel_data.count",
    description="Panel data validation counter",
)


def flatten_request_json(
    request_json: dict, key_prefix: str = "", ignore_keys: list | None = None
) -> dict:
    """Flatten nested JSON into a single-level dict with prefixed lowercase keys."""
    if ignore_keys is None:
        ignore_keys = []
    out: dict = {}
    for k in request_json:
        if k not in ignore_keys:
            if isinstance(request_json[k], dict):
                out.update(flatten_request_json(request_json[k], key_prefix=k))
            else:
                key = key_prefix + "_" + k if key_prefix else k
                out[key.lower()] = request_json[k]
    return out


class EventType:
    """Base class for all event types."""

    def __init__(self, payload: dict):
        """Initialize base event type from payload."""
        self.payload = payload
        self.event_type = payload.get("TvEvent", {}).get("EventType", "")
        self.tvid = payload.get("TvEvent", {}).get("tvid", "")
        self.event_data_params = payload.get("EventData", {})
        self.namespace: str | None = None
        self.appid: str | None = None

    def validate_event_type_payload(self) -> bool:
        """Validate event-specific payload fields."""
        raise NotImplementedError

    def generate_event_data_output_json(self) -> dict:
        """Generate flattened output JSON for the event."""
        raise NotImplementedError


class NativeAppTelemetryEventType(EventType):
    """Handles NATIVEAPP_TELEMETRY events."""

    def __init__(self, payload: dict):
        """Extract namespace and appid from EventData."""
        with tracer.start_as_current_span("NativeAppTelemetryEventType.__init__"):
            super().__init__(payload)
            event_namespace_options = ["Namespace", "NameSpace", "namespace"]
            for option in event_namespace_options:
                if option in self.event_data_params:
                    self.namespace = self.event_data_params[option]

            self.appid = self.event_data_params.get("AppId")

    def validate_event_type_payload(self) -> bool:
        """Validate NativeAppTelemetry payload timestamps."""
        with tracer.start_as_current_span(
            "NativeAppTelemetryEventType.validate_event_type_payload"
        ):
            from app.validation import timestamp_check

            ed_timestamp = self.event_data_params.get("Timestamp")
            if ed_timestamp:
                timestamp_check(ed_timestamp, self.tvid)

            VALIDATE_PAYLOAD_COUNTER.add(1)
            return True

    def generate_event_data_output_json(self) -> dict:
        """Flatten EventData for NativeAppTelemetry output."""
        with tracer.start_as_current_span(
            "NativeAppTelemetryEventType.generate_event_data_output_json"
        ):
            event_data_json = self.payload["EventData"]
            event_data_output: dict = {}
            event_data_output.update(
                flatten_request_json(event_data_json, ignore_keys=["Timestamp"])
            )
            event_data_output["eventdata_timestamp"] = event_data_json["Timestamp"]
            GENERATE_EVENT_DATA_OUTPUT_COUNTER.add(1)
            return event_data_output


class AcrTunerDataEventType(EventType):
    """Handles ACR_TUNER_DATA events."""

    def __init__(self, payload: dict):
        """Extract namespace and appId from TvEvent."""
        with tracer.start_as_current_span("AcrTunerDataEventType.__init__"):
            super().__init__(payload)
            tv_event = payload.get("TvEvent", {})
            event_namespace_options = ["Namespace", "NameSpace", "namespace"]
            for option in event_namespace_options:
                if option in tv_event:
                    self.namespace = tv_event[option]

            self.appid = tv_event.get("appId")

    def validate_event_type_payload(self) -> bool:
        """Validate ACR tuner data with heartbeat and resolution checks."""
        with tracer.start_as_current_span(
            "AcrTunerDataEventType.validate_event_type_payload"
        ):
            is_heartbeat_event = "Heartbeat" in self.event_data_params
            if is_heartbeat_event and self.validate_heartbeat_event():
                ed_params = self.event_data_params["Heartbeat"]
            else:
                optional_params = ["channelData", "programData"]
                if not any(
                    param in self.event_data_params for param in optional_params
                ):
                    msg = (
                        f"Missing Required Param: {optional_params}"
                        f" tvid={self.tvid} EventType={self.event_type}"
                    )
                    raise TvEventsMissingRequiredParamError(msg)
                ed_params = self.event_data_params

            if "channelData" in ed_params:
                req_channel_data = ["majorId", "minorId"]
                from app.validation import verify_required_params

                verify_required_params(ed_params["channelData"], req_channel_data)

            if "resolution" in ed_params:
                req_resolution = ["vRes", "hRes"]
                from app.validation import verify_required_params

                verify_required_params(ed_params["resolution"], req_resolution)

            VALIDATE_PAYLOAD_COUNTER.add(1)
            return True

    def validate_heartbeat_event(self) -> bool:
        """Validate heartbeat event within AcrTunerData."""
        with tracer.start_as_current_span(
            "AcrTunerDataEventType.validate_heartbeat_event"
        ):
            other_params = ["channelData", "programData"]
            if any(param in self.event_data_params for param in other_params):
                msg = (
                    "Heartbeat cannot be sent with"
                    " channel/program Data:"
                    f" tvid={self.tvid}"
                    f" EventType={self.event_type}"
                )
                raise TvEventsInvalidPayloadError(msg)

            hb_params = self.event_data_params["Heartbeat"]
            if not any(param in hb_params for param in other_params):
                msg = (
                    f"Required Heartbeat Param: {other_params}"
                    f" missing: tvid={self.tvid}"
                    f" EventType={self.event_type}"
                )
                raise TvEventsMissingRequiredParamError(msg)

            HEARTBEAT_COUNTER.add(1)
            return True

    def generate_event_data_output_json(self) -> dict:
        """Flatten EventData and convert timestamps for ACR output."""
        with tracer.start_as_current_span(
            "AcrTunerDataEventType.generate_event_data_output_json"
        ):
            from app.validation import timestamp_check, unix_time_to_ms

            event_data_json = self.payload["EventData"]
            event_data_output: dict = {}
            event_data_output.update(flatten_request_json(event_data_json))

            if "programdata_starttime" in event_data_output and timestamp_check(
                event_data_output["programdata_starttime"], self.tvid, is_ms=False
            ):
                event_data_output["programdata_starttime"] = unix_time_to_ms(
                    event_data_output["programdata_starttime"]
                )

            if event_data_json.get("Heartbeat"):
                LOGGER.debug("Heartbeat event received for tvid=%s", self.tvid)
                event_data_output["eventtype"] = "Heartbeat"

            GENERATE_EVENT_DATA_OUTPUT_COUNTER.add(1)
            return event_data_output


class PlatformTelemetryEventType(EventType):
    """Handles PLATFORM_TELEMETRY events."""

    def __init__(self, payload: dict):
        """Initialize PlatformTelemetry from payload."""
        with tracer.start_as_current_span("PlatformTelemetryEventType.__init__"):
            super().__init__(payload)

    panel_data_schema = {
        "required": ["Timestamp", "PanelState", "WakeupReason"],
        "type": "object",
        "properties": {
            "Timestamp": {"type": "number"},
            "PanelState": {"type": "string", "pattern": "^(ON|OFF|on|off|On|Off)$"},
            "WakeupReason": {"type": "number", "minimum": 0, "maximum": 128},
        },
    }

    platform_telemetry_schema = {
        "required": ["PanelData"],
        "type": "object",
        "properties": {"PanelData": panel_data_schema},
    }

    def validate_event_type_payload(self) -> bool:
        """Validate PlatformTelemetry against JSON schema."""
        with tracer.start_as_current_span(
            "PlatformTelemetryEventType.validate_event_type_payload"
        ):
            try:
                validate(
                    instance=self.event_data_params,
                    schema=self.platform_telemetry_schema,
                )
                self.validate_panel_data()
            except ValidationError as e:
                if e.validator == "required":
                    msg = (
                        f"Missing Required Param: {e.message.split()[0]}"
                        f" tvid={self.tvid}"
                        f" EventType={self.event_type}"
                    )
                    raise TvEventsMissingRequiredParamError(msg) from e
                else:
                    msg = (
                        f"Invalid Payload: tvid={self.tvid}"
                        f" EventType: {self.event_type},"
                        f" {e.path.pop()}-{e.message}"
                    )
                    raise TvEventsInvalidPayloadError(msg) from e

            VALIDATE_PAYLOAD_COUNTER.add(1)
            return True

    def validate_panel_data(self) -> bool:
        """Validate PanelData sub-schema and timestamp."""
        with tracer.start_as_current_span(
            "PlatformTelemetryEventType.validate_panel_data"
        ):
            from app.validation import timestamp_check

            pd_params = self.event_data_params["PanelData"]
            validate(instance=pd_params, schema=self.panel_data_schema)
            timestamp_check(pd_params["Timestamp"], self.tvid)

            VERIFY_PANEL_DATA_COUNTER.add(1)
            return True

    def generate_event_data_output_json(self) -> dict:
        """Flatten EventData and normalize PanelState for output."""
        with tracer.start_as_current_span(
            "PlatformTelemetryEventType.generate_event_data_output_json"
        ):
            event_data_json = self.payload["EventData"]
            event_data_output: dict = {}
            event_data_output.update(flatten_request_json(event_data_json))

            event_data_output["paneldata_panelstate"] = event_data_output[
                "paneldata_panelstate"
            ].upper()

            GENERATE_EVENT_DATA_OUTPUT_COUNTER.add(1)
            return event_data_output


event_type_map = {
    "NATIVEAPP_TELEMETRY": NativeAppTelemetryEventType,
    "ACR_TUNER_DATA": AcrTunerDataEventType,
    "PLATFORM_TELEMETRY": PlatformTelemetryEventType,
}
