"""Tests for tvevents.domain.validation module."""

import pytest

from tests.conftest import make_valid_hash, make_valid_payload


class TestVerifyRequiredParams:
    """Tests for verify_required_params."""

    def test_all_params_present(self) -> None:
        from tvevents.domain.validation import verify_required_params

        payload = make_valid_payload()
        assert verify_required_params(payload) is True

    def test_missing_tvid_raises(self) -> None:
        from tvevents.domain.validation import (
            TvEventsMissingRequiredParamError,
            verify_required_params,
        )

        payload = make_valid_payload()
        del payload["TvEvent"]["tvid"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="tvid"):
            verify_required_params(payload)

    def test_missing_h_raises(self) -> None:
        from tvevents.domain.validation import (
            TvEventsMissingRequiredParamError,
            verify_required_params,
        )

        payload = make_valid_payload()
        del payload["TvEvent"]["h"]
        with pytest.raises(TvEventsMissingRequiredParamError, match="h"):
            verify_required_params(payload)

    def test_custom_required_params(self) -> None:
        from tvevents.domain.validation import verify_required_params

        data = {"foo": 1, "bar": 2}
        assert verify_required_params(data, ["foo", "bar"]) is True

    def test_custom_missing_param(self) -> None:
        from tvevents.domain.validation import (
            TvEventsMissingRequiredParamError,
            verify_required_params,
        )

        data = {"foo": 1}
        with pytest.raises(TvEventsMissingRequiredParamError, match="bar"):
            verify_required_params(data, ["foo", "bar"])


class TestTimestampCheck:
    """Tests for timestamp_check."""

    def test_valid_ms_timestamp(self) -> None:
        from tvevents.domain.validation import timestamp_check

        assert timestamp_check(1700000000000, "tv1") is True

    def test_valid_seconds_timestamp(self) -> None:
        from tvevents.domain.validation import timestamp_check

        assert timestamp_check(1700000000, "tv1", is_ms=False) is True

    def test_none_returns_none(self) -> None:
        from tvevents.domain.validation import timestamp_check

        assert timestamp_check(None, "tv1") is None

    def test_empty_string_returns_none(self) -> None:
        from tvevents.domain.validation import timestamp_check

        assert timestamp_check("", "tv1") is None

    def test_invalid_timestamp_raises(self) -> None:
        from tvevents.domain.validation import (
            TvEventsInvalidPayloadError,
            timestamp_check,
        )

        with pytest.raises(TvEventsInvalidPayloadError, match="Timestamp check failed"):
            timestamp_check("not-a-number", "tv1")


class TestParamsMatchCheck:
    """Tests for params_match_check."""

    def test_matching_params(self) -> None:
        from tvevents.domain.validation import params_match_check

        assert params_match_check("tvid", "abc", "abc") is True

    def test_mismatched_params(self) -> None:
        from tvevents.domain.validation import params_match_check

        assert params_match_check("tvid", "abc", "def") is False


class TestValidateSecurityHash:
    """Tests for validate_security_hash."""

    def test_valid_hash_passes(self) -> None:
        from tvevents.domain.validation import validate_security_hash

        tvid = "device-001"
        salt = "test-salt"
        h = make_valid_hash(tvid, salt)
        assert validate_security_hash(tvid, h, salt) is True

    def test_invalid_hash_raises(self) -> None:
        from tvevents.domain.validation import (
            TvEventsSecurityValidationError,
            validate_security_hash,
        )

        with pytest.raises(TvEventsSecurityValidationError):
            validate_security_hash("device-001", "bad-hash", "test-salt")


class TestValidateRequest:
    """Tests for validate_request."""

    def test_valid_request(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.validation import validate_request

        payload = make_valid_payload()
        url_params = {"tvid": "test-tvid-001", "event_type": "ACR_TUNER_DATA"}
        assert validate_request(url_params, payload, "test-salt", EVENT_TYPE_MAP) is True

    def test_missing_required_param_raises(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.validation import (
            TvEventsMissingRequiredParamError,
            validate_request,
        )

        payload = make_valid_payload()
        del payload["TvEvent"]["client"]
        url_params = {"tvid": "test-tvid-001", "event_type": "ACR_TUNER_DATA"}
        with pytest.raises(TvEventsMissingRequiredParamError):
            validate_request(url_params, payload, "test-salt", EVENT_TYPE_MAP)

    def test_invalid_hash_raises(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.validation import (
            TvEventsSecurityValidationError,
            validate_request,
        )

        payload = make_valid_payload()
        payload["TvEvent"]["h"] = "wrong-hash"
        url_params = {"tvid": "test-tvid-001", "event_type": "ACR_TUNER_DATA"}
        with pytest.raises(TvEventsSecurityValidationError):
            validate_request(url_params, payload, "test-salt", EVENT_TYPE_MAP)
