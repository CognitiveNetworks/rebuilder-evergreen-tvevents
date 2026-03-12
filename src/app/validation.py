"""Request validation and T1_SALT security hash verification."""

import datetime
import os

from cnlib.cnlib import token_hash
from opentelemetry import trace

from app import configure_logging, meter
from app.event_type import event_type_map
from app.exceptions import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
    TvEventsSecurityValidationError,
)

LOGGER = configure_logging()
tracer = trace.get_tracer(__name__)

REQUIRED_PARAMS = ("tvid", "client", "h", "EventType", "timestamp")
SALT_KEY = os.environ.get("T1_SALT")

VALIDATION_FAILURE_COUNTER = meter.create_counter(
    name="validation.failure.count",
    description="Validation failure counter",
)


def verify_required_params(
    payload: dict, required_params: tuple | list = REQUIRED_PARAMS
) -> bool:
    """Check that all required params exist in the payload's TvEvent sub-dict."""
    check_payload = payload.get("TvEvent", payload)
    for param in required_params:
        if param not in check_payload:
            VALIDATION_FAILURE_COUNTER.add(1, {"reason": "missing_param"})
            raise TvEventsMissingRequiredParamError(f"Missing Required Param: {param}")
    return True


def timestamp_check(ts, tvid: str, is_ms: bool = True) -> bool:
    """Validate that a timestamp is parseable. Supports ms or s format."""
    try:
        ts = int(ts)
        if is_ms:
            datetime.datetime.fromtimestamp(ts / 1000)
        else:
            datetime.datetime.fromtimestamp(ts)
        return True
    except Exception as e:
        VALIDATION_FAILURE_COUNTER.add(1, {"reason": "invalid_timestamp"})
        raise TvEventsInvalidPayloadError(
            f"Timestamp check failed: tvid={tvid} ts={ts} with error {e}"
        ) from e


def unix_time_to_ms(ts) -> int:
    """Convert a timestamp to milliseconds."""
    return ts * 1000


def params_match_check(param_name: str, url_param, payload_param) -> bool:
    """Verify duplicate params in URL and payload match."""
    if url_param != payload_param:
        LOGGER.warning(
            "%s Mismatch. Request url and payload params do not match [%s != %s]",
            param_name,
            url_param,
            payload_param,
        )
    return url_param == payload_param


def get_event_type_mapping(event_type: str):
    """Return the EventType class for a given event_type string, or None."""
    mapping = None
    try:
        mapping = event_type_map[event_type]
    except KeyError:
        LOGGER.warning(
            "generate_output: Mapping for EventType %s does not exist",
            event_type,
        )
    return mapping


def validate_security_hash(tvid: str, h_value: str) -> bool:
    """Validate the T1_SALT security hash for the given tvid and h_value."""
    if not token_hash.security_hash_match(tvid, h_value, SALT_KEY):
        VALIDATION_FAILURE_COUNTER.add(1, {"reason": "security_hash"})
        raise TvEventsSecurityValidationError(
            f"Security hash decryption failure for tvid={tvid}."
        )
    return True


def validate_request(url_params: dict, payload: dict) -> bool:
    """
    Full validation pipeline for an incoming request.

    Checks: required params, param match, timestamp, security hash, event type payload.
    """
    tvid = url_params.get("tvid")

    LOGGER.debug("validate_request")
    verify_required_params(payload)

    payload_event_type = payload["TvEvent"]["EventType"]
    params_match_check("tvid", tvid, payload["TvEvent"]["tvid"])
    params_match_check("event_type", url_params.get("event_type"), payload_event_type)

    payload_event_timestamp = payload["TvEvent"]["timestamp"]
    timestamp_check(payload_event_timestamp, str(tvid))

    # validate tv hash
    h_value = payload["TvEvent"]["h"]
    validate_security_hash(str(tvid), str(h_value))

    # validate EventData for payload EventType
    et_map = get_event_type_mapping(payload_event_type)
    if et_map:
        et_object = et_map(payload)
        et_object.validate_event_type_payload()

    LOGGER.debug("validate_request completed")
    return True
