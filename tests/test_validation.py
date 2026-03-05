"""Validation tests — required params, timestamps, HMAC, param matching.

Exercises the domain validation layer with realistic Vizio Smart TV payloads.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import pytest

from tests.conftest import TEST_SALT, TVID_1
from tvevents.domain.validation import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
    TvEventsSecurityValidationError,
    params_match_check,
    timestamp_check,
    validate_request,
    validate_security_hash,
    verify_required_params,
)


class TestSmartTvRequestValidation:
    """Validate that Smart TV event payloads are accepted or rejected
    according to the legacy rules: required params, timestamp format,
    security hash, and param matching between URL and body."""

    # ── Required params ──────────────────────────────────────────────

    def test_tv_with_all_required_params_accepted(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends a complete ACR_TUNER_DATA payload with all required
        TvEvent fields (tvid, client, h, EventType, timestamp) —
        verify_required_params returns True."""
        assert verify_required_params(sample_acr_tuner_payload) is True

    def test_tv_missing_tvid_rejected(self, sample_acr_tuner_payload: dict[str, Any]) -> None:
        """TV sends payload without tvid → TvEventsMissingRequiredParamError
        with message indicating 'tvid'."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["TvEvent"]["tvid"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="tvid"):
            verify_required_params(payload)

    def test_tv_missing_client_rejected(self, sample_acr_tuner_payload: dict[str, Any]) -> None:
        """TV sends payload without client → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["TvEvent"]["client"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="client"):
            verify_required_params(payload)

    def test_tv_missing_security_hash_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends payload without h (security hash) → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["TvEvent"]["h"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="h"):
            verify_required_params(payload)

    def test_tv_missing_event_type_rejected(
        self, sample_acr_tuner_payload: dict[str, Any]
    ) -> None:
        """TV sends payload with EventType omitted → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["TvEvent"]["EventType"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="EventType"):
            verify_required_params(payload)

    def test_tv_missing_timestamp_rejected(self, sample_acr_tuner_payload: dict[str, Any]) -> None:
        """TV sends payload with timestamp omitted → MissingRequiredParamError."""
        payload = deepcopy(sample_acr_tuner_payload)
        del payload["TvEvent"]["timestamp"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="timestamp"):
            verify_required_params(payload)

    # ── Timestamp validation ─────────────────────────────────────────

    def test_tv_with_valid_millisecond_timestamp_accepted(self) -> None:
        """Timestamp 1709568000000 (2024-03-04 16:00 UTC in ms) passes
        timestamp_check with is_ms=True."""
        result = timestamp_check(1709568000000, TVID_1, is_ms=True)
        assert result is True

    def test_tv_with_valid_seconds_timestamp_accepted(self) -> None:
        """Timestamp 1709568000 (seconds) passes with is_ms=False."""
        result = timestamp_check(1709568000, TVID_1, is_ms=False)
        assert result is True

    def test_tv_with_null_timestamp_returns_none(self) -> None:
        """Null timestamp returns None — not an exception — allowing
        optional timestamp scenarios."""
        result = timestamp_check(None, TVID_1)
        assert result is None

    def test_tv_with_empty_string_timestamp_returns_none(self) -> None:
        """Empty-string timestamp returns None, matching legacy behaviour."""
        result = timestamp_check("", TVID_1)
        assert result is None

    def test_tv_with_invalid_timestamp_rejected(self) -> None:
        """Non-numeric junk in timestamp → TvEventsInvalidPayloadError."""
        with pytest.raises(TvEventsInvalidPayloadError, match="Timestamp check failed"):
            timestamp_check("not-a-timestamp", TVID_1)

    # ── Security hash (HMAC) ─────────────────────────────────────────

    def test_security_hash_matches_for_known_tvid(self, valid_hmac_hash) -> None:
        """Compute HMAC-SHA256 for ITV00C000000000000001 with test salt,
        then validate_security_hash succeeds."""
        h = valid_hmac_hash(TVID_1)
        assert validate_security_hash(TVID_1, h, TEST_SALT) is True

    def test_security_hash_mismatch_raises_error(self) -> None:
        """HMAC computed with wrong key → TvEventsSecurityValidationError."""
        wrong_hash = "0" * 64
        with pytest.raises(
            TvEventsSecurityValidationError, match="Security hash decryption failure"
        ):
            validate_security_hash(TVID_1, wrong_hash, TEST_SALT)

    # ── Param match check ────────────────────────────────────────────

    def test_tvid_mismatch_between_url_and_payload_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """URL tvid=ITV00C000000000000001, payload tvid=ITV00CDIFFERENTID
        → params_match_check returns False and logs a warning."""
        with caplog.at_level(logging.WARNING):
            result = params_match_check(
                "tvid",
                "ITV00C000000000000001",
                "ITV00CDIFFERENTID000002",
            )
        assert result is False
        assert "Mismatch" in caplog.text

    def test_event_type_mismatch_between_url_and_payload_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """URL event_type=ACR_TUNER_DATA, payload EventType=PLATFORM_TELEMETRY
        → returns False, warning logged."""
        with caplog.at_level(logging.WARNING):
            result = params_match_check(
                "event_type",
                "ACR_TUNER_DATA",
                "PLATFORM_TELEMETRY",
            )
        assert result is False
        assert "Mismatch" in caplog.text

    # ── Full chain orchestration ─────────────────────────────────────

    def test_full_request_validation_orchestration(
        self, sample_acr_tuner_payload: dict[str, Any], settings
    ) -> None:
        """validate_request exercises the full chain: required params,
        param match, timestamp, HMAC, event-type-specific validation —
        a valid ACR_TUNER_DATA payload passes all checks."""
        url_params = {
            "tvid": TVID_1,
            "event_type": "ACR_TUNER_DATA",
        }
        result = validate_request(url_params, sample_acr_tuner_payload, TEST_SALT)
        assert result is True
