"""Request validation logic — ported from legacy app/utils.py."""


import datetime
import logging
from typing import Any

from tvevents.domain.security import security_hash_match

logger = logging.getLogger(__name__)

REQUIRED_PARAMS = ("tvid", "client", "h", "EventType", "timestamp")


class TvEventsDefaultException(Exception):
    """Base exception for custom TvEvents errors."""

    status_code = 400


class TvEventsCatchallException(TvEventsDefaultException):
    """Error when something goes wrong within route execution."""


class TvEventsMissingRequiredParamError(TvEventsDefaultException):
    """Error when a required param is not provided."""


class TvEventsSecurityValidationError(TvEventsDefaultException):
    """Error when security hash verification fails."""


class TvEventsInvalidPayloadError(TvEventsDefaultException):
    """Error when payload is not valid."""


def verify_required_params(
    payload: dict[str, Any],
    required_params: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """Ensure all required params are present in the payload.

    If payload contains a 'TvEvent' key, checks inside that dict.
    """
    required = required_params or REQUIRED_PARAMS
    payload_params = payload.get("TvEvent", payload)
    for req_param in required:
        if req_param not in payload_params:
            msg = f"Missing Required Param: {req_param}"
            raise TvEventsMissingRequiredParamError(msg)
    return True


def timestamp_check(ts: Any, tvid: str, is_ms: bool = True) -> bool | None:
    """Validate that a timestamp is a valid Unix timestamp."""
    if ts is None or ts == "":
        return None
    try:
        if is_ms:
            datetime.datetime.fromtimestamp(ts / 1000)
        else:
            datetime.datetime.fromtimestamp(ts)
        return True
    except Exception as e:
        raise TvEventsInvalidPayloadError(
            f"Timestamp check failed: tvid={tvid} ts={ts} with error {e}"
        ) from e


def unix_time_to_ms(ts: int | float) -> int | float:
    """Convert a timestamp from seconds to milliseconds."""
    return ts * 1000


def params_match_check(param_name: str, url_param: Any, payload_param: Any) -> bool:
    """Check that duplicate params in URL and payload match."""
    if url_param != payload_param:
        logger.warning(
            "%s Mismatch. Request url and payload params do not match [%s != %s]",
            param_name,
            url_param,
            payload_param,
        )
    return url_param == payload_param


def validate_security_hash(tvid: str, h_value: str, salt: str) -> bool:
    """Validate the security hash for the given tvid."""
    if not security_hash_match(tvid, h_value, salt):
        raise TvEventsSecurityValidationError(
            f"Security hash decryption failure for tvid={tvid}."
        )
    return True


def validate_request(
    url_params: dict[str, Any],
    payload: dict[str, Any],
    salt: str,
    event_type_map: dict[str, Any],
) -> bool:
    """Run all validation checks on the incoming request.

    Checks required params, param consistency, timestamp, security hash,
    and event-type-specific validation.
    """
    tvid = url_params.get("tvid", "")

    logger.debug("validate_request")
    verify_required_params(payload)

    payload_event_type = payload["TvEvent"]["EventType"]
    params_match_check("tvid", tvid, payload["TvEvent"]["tvid"])
    params_match_check("event_type", url_params.get("event_type"), payload_event_type)

    payload_event_timestamp = payload["TvEvent"]["timestamp"]
    timestamp_check(payload_event_timestamp, tvid)

    h_value = payload["TvEvent"]["h"]
    validate_security_hash(tvid, h_value, salt)

    et_class = event_type_map.get(payload_event_type)
    if et_class:
        et_object = et_class(payload)
        et_object.validate_event_type_payload()

    logger.debug("validate_request completed")
    return True
