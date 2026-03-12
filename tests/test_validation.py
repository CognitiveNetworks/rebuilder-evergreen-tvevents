"""Tests for app.validation module."""

import time

import pytest

from app.exceptions import (
    TvEventsInvalidPayloadError,
    TvEventsMissingRequiredParamError,
    TvEventsSecurityValidationError,
)
from app.validation import (
    get_event_type_mapping,
    params_match_check,
    timestamp_check,
    unix_time_to_ms,
    validate_request,
    validate_security_hash,
    verify_required_params,
)


class TestVerifyRequiredParams:
    def test_valid_payload_passes(self, sample_nativeapp_payload):
        verify_required_params(sample_nativeapp_payload)

    def test_missing_param_raises(self):
        payload = {"TvEvent": {"tvid": "abc"}}
        with pytest.raises(TvEventsMissingRequiredParamError):
            verify_required_params(payload)


class TestTimestampCheck:
    def test_valid_ms_timestamp(self):
        ts_ms = str(int(time.time() * 1000))
        timestamp_check(ts_ms, "tvid-001", is_ms=True)

    def test_valid_seconds_timestamp(self):
        ts_s = str(int(time.time()))
        timestamp_check(ts_s, "tvid-001", is_ms=False)

    def test_non_numeric_timestamp_raises(self):
        with pytest.raises(TvEventsInvalidPayloadError):
            timestamp_check("not_a_number", "tvid-001", is_ms=True)


class TestUnixTimeToMs:
    def test_seconds_to_ms(self):
        result = unix_time_to_ms(1700000000)
        assert result == 1700000000000

    def test_always_multiplies(self):
        result = unix_time_to_ms(1700000000000)
        assert result == 1700000000000000


class TestParamsMatchCheck:
    def test_matching_params(self):
        params_match_check("tvid", "abc", "abc")

    def test_mismatched_params_returns_false(self):
        result = params_match_check("tvid", "abc", "xyz")
        assert result is False


class TestGetEventTypeMapping:
    def test_valid_event_type(self):
        result = get_event_type_mapping("NATIVEAPP_TELEMETRY")
        assert result is not None

    def test_invalid_event_type_returns_none(self):
        result = get_event_type_mapping("INVALID_TYPE")
        assert result is None


class TestValidateSecurityHash:
    def test_valid_hash(self, mock_security_hash):
        mock_security_hash.security_hash_match.return_value = True
        validate_security_hash("tvid-001", "valid_hash")

    def test_invalid_hash_raises(self, mock_security_hash):
        mock_security_hash.security_hash_match.return_value = False
        with pytest.raises(TvEventsSecurityValidationError):
            validate_security_hash("tvid-001", "bad_hash")


class TestValidateRequest:
    def test_valid_request(
        self, sample_url_params, sample_nativeapp_payload, mock_security_hash
    ):
        validate_request(sample_url_params, sample_nativeapp_payload)

    def test_missing_payload_params_raises(self, sample_url_params, mock_security_hash):
        bad_payload = {"TvEvent": {"tvid": "VZR2023A7F4E9B01"}}
        with pytest.raises(TvEventsMissingRequiredParamError):
            validate_request(sample_url_params, bad_payload)
