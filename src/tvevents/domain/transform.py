"""Payload flattening and output generation — ported from legacy app/utils.py."""


import logging
from typing import Any

logger = logging.getLogger(__name__)


def flatten_request_json(
    request_json: dict[str, Any],
    key_prefix: str = "",
    ignore_keys: list[str] | str | None = None,
) -> dict[str, Any]:
    """Flatten nested request JSON into a single-level dict with lowercased keys.

    Ported from legacy utils.flatten_request_json.
    """
    if ignore_keys is None:
        ignore_keys = []
    elif isinstance(ignore_keys, str):
        ignore_keys = [ignore_keys]

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
    """Extract namespace from payload, checking multiple key variations."""
    namespace: str | None = None
    for option in ("Namespace", "NameSpace", "namespace"):
        if option in payload:
            namespace = payload[option]
    return namespace


def generate_output_json(
    request_json: dict[str, Any],
    zoo: str,
    event_type_map: dict[str, Any],
) -> dict[str, Any]:
    """Generate flattened output JSON for the given payload.

    Ported from legacy utils.generate_output_json.
    """
    try:
        request_event_type = request_json["TvEvent"]["EventType"]
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

        et_class = event_type_map.get(output_json["tvevent_eventtype"])
        if et_class:
            et_object = et_class(request_json)
            event_type_output_json = et_object.generate_event_data_output_json()
            output_json.update(event_type_output_json)
            output_json["namespace"] = et_object.namespace
            output_json["appid"] = et_object.appid
        else:
            output_json.update(flatten_request_json(request_json["EventData"]))

        return output_json
    except KeyError as ke:
        logger.error(
            "generate_output failed: Missing %s, %s", ke, request_json
        )
        raise
    except Exception as e:
        logger.error("Unhandled exception in generate_output: %s", e)
        raise
