# pylint: disable=E0401,W0621,R0801
import pytest
from app.utils import timestamp_check, TvEventsInvalidPayloadError


def test_timestamp_check_valid_ms():
    """
    Test timestamp_check with a valid millisecond timestamp.
    """
    assert timestamp_check(1609459200000, 12345) is True


def test_timestamp_check_valid_s():
    """
    Test timestamp_check with a valid second timestamp.
    """
    assert timestamp_check(1609459200, 12345, is_ms=False) is True


def test_timestamp_check_invalid_ms():
    """
    Test timestamp_check with an invalid millisecond
    timestamp that should raise TvEventsInvalidPayloadError.
    """
    with pytest.raises(TvEventsInvalidPayloadError):
        timestamp_check(999999999999999, '12345')


def test_timestamp_check_none():
    """
    Test timestamp_check with None as input, which should return None.
    """
    assert timestamp_check(None, '12345') is None


def test_timestamp_check_empty_string():
    """
    Test timestamp_check with an empty string as input, which should return None.
    """
    assert timestamp_check('', '12345') is None


def test_timestamp_check_string():
    """
    Test timestamp_check with an invalid string as input,
    which should raise TvEventsInvalidPayloadError.
    """
    with pytest.raises(TvEventsInvalidPayloadError):
        timestamp_check('invalid_string', '12345')
