"""Event-type processing — polymorphic validation and output generation.

Each supported ``EventType`` has a class that knows how to *validate* the
incoming ``EventData`` and *generate* the flattened output JSON that
downstream consumers depend on.

**All logic is a faithful port of the legacy ``event_type.py`` and the
helper functions from ``utils.py``.**
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from tvevents.domain.validation import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
    timestamp_check,
    unix_time_to_ms,
    verify_required_params,
)

logger = logging.getLogger(__name__)


# ── Shared helpers (legacy utils.py) ─────────────────────────────────────


def flatten_request_json(
    request_json: dict[str, Any],
    key_prefix: str = "",
    ignore_keys: Any = None,
) -> dict[str, Any]:
    """Recursively flatten nested dicts with underscore-prefixed, lowercased keys.

    This preserves the **exact** semantics of the legacy implementation,
    including the behaviour when ``ignore_keys`` is a plain string (the
    ``in`` operator performs a substring check rather than a membership
    check).  That quirk is intentional — changing it would alter which
    keys are included in the output JSON.

    Parameters
    ----------
    request_json:
        The nested dict to flatten.
    key_prefix:
        Prefix prepended (with ``_``) to each output key.
    ignore_keys:
        Keys to skip.  May be a ``list`` (membership check) **or** a
        ``str`` (substring check — legacy compat).
    """
    if ignore_keys is None:
        ignore_keys = []

    out: dict[str, Any] = {}
    for k in request_json:
        if k not in ignore_keys:
            if isinstance(request_json[k], dict):
                out.update(flatten_request_json(request_json[k], key_prefix=k))
            else:
                key = f"{key_prefix}_{k}" if key_prefix else k
                out[key.lower()] = request_json[k]
    return out


def get_payload_namespace(payload: dict[str, Any]) -> str | None:
    """Extract namespace from *payload*, checking three casing variants.

    Returns the first match among ``Namespace``, ``NameSpace``,
    ``namespace``; ``None`` if none found.
    """
    for option in ("Namespace", "NameSpace", "namespace"):
        if option in payload:
            return payload[option]  # type: ignore[no-any-return]
    return None


def get_event_type_mapping(event_type: str) -> type[EventType] | None:
    """Return the :class:`EventType` subclass for *event_type*, or ``None``."""
    mapping: type[EventType] | None = None
    try:
        mapping = event_type_map[event_type]
    except KeyError as ke:
        logger.warning(
            "generate_output: Mapping for EventType %s does not exist %s",
            event_type,
            ke,
        )
    return mapping


def generate_output_json(
    request_json: dict[str, Any],
    zoo: str,
) -> dict[str, Any]:
    """Generate the canonical flattened output JSON for an ingested event.

    The output format is a **downstream contract** — key names, nesting,
    and value transformations must match the legacy service byte-for-byte.

    Parameters
    ----------
    request_json:
        The full request body (containing ``TvEvent`` and ``EventData``).
    zoo:
        Environment name injected into the output.
    """
    try:
        request_event_type: str = request_json["TvEvent"]["EventType"]
        output_json: dict[str, Any] = {}

        output_json.update(
            flatten_request_json(
                request_json["TvEvent"],
                ignore_keys=["h", "timestamp", "EventType"],
            )
        )
        output_json["tvevent_timestamp"] = request_json["TvEvent"]["timestamp"]
        output_json["tvevent_eventtype"] = request_event_type
        output_json["zoo"] = zoo

        et_map = get_event_type_mapping(output_json["tvevent_eventtype"])

        if et_map:
            et_object = et_map(request_json)
            event_type_output_json = et_object.generate_event_data_output_json()
            output_json.update(event_type_output_json)
            output_json["namespace"] = et_object.namespace
            output_json["appid"] = et_object.appid
        else:
            output_json.update(flatten_request_json(request_json["EventData"]))

        return output_json
    except KeyError as ke:
        logger.error(
            "generate_output failed: Missing %s, %s",
            ke,
            request_json,
        )
        raise
    except Exception as exc:
        logger.error("Unhandled exception in generate_output: %s", exc)
        raise


# ── EventType base class ─────────────────────────────────────────────────


class EventType:
    """Abstract base for event-type-specific processing."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.event_type: str = payload["TvEvent"]["EventType"]
        self.tvid: str = payload["TvEvent"]["tvid"]
        self.event_data_params: dict[str, Any] = self.payload["EventData"]
        self.namespace: str | None = None
        self.appid: str | None = None

    @abstractmethod
    def validate_event_type_payload(self) -> bool:
        """Ensure required fields for this event type are present."""
        ...

    @abstractmethod
    def generate_event_data_output_json(self) -> dict[str, Any]:
        """Generate flattened output JSON for ``EventData``."""
        ...


# ── NATIVEAPP_TELEMETRY ──────────────────────────────────────────────────


class NativeAppTelemetryEventType(EventType):
    """Handles ``NATIVEAPP_TELEMETRY`` events."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)
        self.namespace = get_payload_namespace(self.event_data_params)
        self.appid: str | None = self.event_data_params.get("AppId")

    def validate_event_type_payload(self) -> bool:
        req_fields = ["Timestamp"]
        verify_required_params(self.event_data_params, req_fields)
        timestamp_check(self.event_data_params["Timestamp"], self.tvid)
        return True

    def generate_event_data_output_json(self) -> dict[str, Any]:
        event_data_json: dict[str, Any] = self.payload["EventData"]
        event_data_output: dict[str, Any] = {}

        # NOTE: ignore_keys is a *string* here — this is the legacy behaviour.
        # The ``in`` operator in ``flatten_request_json`` therefore performs a
        # **substring** check (e.g. 'T' in 'Timestamp' == True).  See the
        # docstring in ``flatten_request_json`` for details.
        event_data_output.update(flatten_request_json(event_data_json, ignore_keys="Timestamp"))
        event_data_output["eventdata_timestamp"] = event_data_json["Timestamp"]
        return event_data_output


# ── ACR_TUNER_DATA ───────────────────────────────────────────────────────


class AcrTunerDataEventType(EventType):
    """Handles ``ACR_TUNER_DATA`` events including heartbeat sub-type."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)
        self.namespace = get_payload_namespace(self.payload["TvEvent"])
        self.appid: str | None = self.payload["TvEvent"].get("appId")

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
        """Validate heartbeat event constraints."""
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
        event_data_json: dict[str, Any] = self.payload["EventData"]
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


# ── PLATFORM_TELEMETRY ───────────────────────────────────────────────────


class PlatformTelemetryEventType(EventType):
    """Handles ``PLATFORM_TELEMETRY`` events with PanelData schema validation."""

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

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload)

    def validate_event_type_payload(self) -> bool:
        try:
            validate(
                instance=self.event_data_params,
                schema=self.platform_telemetry_schema,
            )
            self._validate_panel_data()
        except ValidationError as exc:
            if exc.validator == "required":
                msg = (
                    f"Missing Required Param: {exc.message.split()[0]} "
                    f"tvid={self.tvid} EventType={self.event_type}"
                )
                raise TvEventsMissingRequiredParamError(msg) from exc
            else:
                msg = (
                    f"Invalid Payload: tvid={self.tvid} EventType: "
                    f"{self.event_type}, {exc.path.pop()}-{exc.message}"
                )
                raise TvEventsInvalidPayloadError(msg) from exc
        return True

    def _validate_panel_data(self) -> bool:
        """Validate PanelData sub-object and its timestamp."""
        pd_params = self.event_data_params["PanelData"]
        validate(instance=pd_params, schema=self.panel_data_schema)
        timestamp_check(pd_params["Timestamp"], self.tvid)
        return True

    def generate_event_data_output_json(self) -> dict[str, Any]:
        event_data_json: dict[str, Any] = self.payload["EventData"]
        event_data_output: dict[str, Any] = {}
        event_data_output.update(flatten_request_json(event_data_json))
        event_data_output["paneldata_panelstate"] = event_data_output[
            "paneldata_panelstate"
        ].upper()
        return event_data_output


# ── Dispatch map ─────────────────────────────────────────────────────────

event_type_map: dict[str, type[EventType]] = {
    "NATIVEAPP_TELEMETRY": NativeAppTelemetryEventType,
    "ACR_TUNER_DATA": AcrTunerDataEventType,
    "PLATFORM_TELEMETRY": PlatformTelemetryEventType,
}
