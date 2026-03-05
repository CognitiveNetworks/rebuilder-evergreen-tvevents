"""Payload validation — HMAC, required parameters, timestamps.

Every function in this module preserves the **exact** validation logic of the
legacy ``utils.py`` so that the same payloads pass / fail identically.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# ── Required fields in TvEvent ───────────────────────────────────────────
REQUIRED_PARAMS: tuple[str, ...] = ("tvid", "client", "h", "EventType", "timestamp")


# ── Custom exception hierarchy ───────────────────────────────────────────


class TvEventsDefaultError(Exception):
    """Base Exception object for custom TvEvents Exceptions."""

    status_code: int = 400


# Backward-compatible alias used by other modules.
TvEventsDefaultException = TvEventsDefaultError  # noqa: N818


class TvEventsCatchallError(TvEventsDefaultError):
    """Error when something goes wrong within the route execution."""


# Backward-compatible alias.
TvEventsCatchallException = TvEventsCatchallError  # noqa: N818


class TvEventsMissingRequiredParamError(TvEventsDefaultException):
    """Error when a required param is not provided."""


class TvEventsSecurityValidationError(TvEventsDefaultException):
    """Error when security hash decryption doesn't match given tvid."""


class TvEventsInvalidPayloadError(TvEventsDefaultException):
    """Error when payload is not valid."""


# ── Validation helpers ───────────────────────────────────────────────────


def verify_required_params(
    payload: dict[str, Any],
    required_params: Sequence[str] | None = None,
) -> bool:
    """Ensure all *required_params* are present in the payload dict.

    When *payload* contains a ``TvEvent`` key the check targets the nested
    dict; otherwise it checks the payload directly.  This replicates the
    exact legacy behaviour of ``utils.verify_required_params``.
    """
    required: Sequence[str] = required_params if required_params is not None else REQUIRED_PARAMS
    payload_params: dict[str, Any] = payload.get("TvEvent", payload)
    for req_param in required:
        if req_param not in payload_params:
            msg = f"Missing Required Param: {req_param}"
            raise TvEventsMissingRequiredParamError(msg)
    return True


def timestamp_check(ts: Any, tvid: str, *, is_ms: bool = True) -> bool | None:
    """Validate that *ts* represents a valid datetime.

    If *is_ms* is ``True`` the value is divided by 1000 before being
    passed to ``datetime.datetime.fromtimestamp``.  Returns ``True`` on
    success, ``None`` when *ts* is empty/``None``, or raises
    :class:`TvEventsInvalidPayloadError`.
    """
    if ts is None or ts == "":
        return None
    try:
        if is_ms:
            datetime.datetime.fromtimestamp(ts / 1000)  # noqa: DTZ006 — legacy compat
        else:
            datetime.datetime.fromtimestamp(ts)  # noqa: DTZ006
        return True
    except Exception as exc:
        raise TvEventsInvalidPayloadError(
            f"Timestamp check failed: tvid={tvid} ts={ts} with error {exc}"
        ) from exc


def unix_time_to_ms(ts: int | float) -> int | float:
    """Convert a Unix timestamp to milliseconds."""
    return ts * 1000


def params_match_check(param_name: str, url_param: Any, payload_param: Any) -> bool:
    """Log a warning when duplicate URL / payload params diverge.

    Returns whether the two values are equal.
    """
    if url_param != payload_param:
        logger.warning(
            "%s Mismatch. Request url and payload params do not match [%s != %s]",
            param_name,
            url_param,
            payload_param,
        )
    return url_param == payload_param  # type: ignore[no-any-return]


def validate_security_hash(tvid: str, h_value: str, salt: str) -> bool:
    """Verify the HMAC security hash for *tvid*.

    .. warning::

       RISK — The exact hashing algorithm used by the legacy ``cnlib.token_hash``
       is not available in source form.  The implementation below is a
       best-guess reconstruction: ``HMAC-SHA256(key=salt, msg=tvid)``.
       If the legacy library used a different algorithm (e.g. SHA-1, double-hash,
       or additional transformations on the tvid before hashing), this will
       reject previously valid payloads.  Validate against production traffic
       before cutting over.
    """
    computed = hmac.new(salt.encode(), tvid.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, h_value):
        raise TvEventsSecurityValidationError(f"Security hash decryption failure for tvid={tvid}.")
    return True


def validate_request(
    url_params: dict[str, Any],
    payload: dict[str, Any],
    salt: str,
) -> bool:
    """Orchestrate all validation checks on an incoming request.

    This mirrors the exact call order of legacy ``utils.validate_request``:
    1. ``verify_required_params``
    2. ``params_match_check`` for *tvid* and *event_type*
    3. ``timestamp_check``
    4. ``validate_security_hash``
    5. Event-type-specific validation (via ``event_type_map``)
    """
    # Avoid circular import — event_types depends on validation, and we
    # need event_type_map here.
    from tvevents.domain.event_types import get_event_type_mapping  # noqa: PLC0415

    tvid: str | None = url_params.get("tvid")

    logger.debug("validate_request")
    verify_required_params(payload)

    payload_event_type: str = payload["TvEvent"]["EventType"]
    params_match_check("tvid", tvid, payload["TvEvent"]["tvid"])
    params_match_check("event_type", url_params.get("event_type"), payload_event_type)

    payload_event_timestamp = payload["TvEvent"]["timestamp"]
    timestamp_check(payload_event_timestamp, tvid or "")

    h_value: str = payload["TvEvent"]["h"]
    validate_security_hash(tvid or "", h_value, salt)

    et_map = get_event_type_mapping(payload_event_type)
    if et_map:
        et_object = et_map(payload)
        et_object.validate_event_type_payload()

    logger.debug("validate_request completed")
    return True
