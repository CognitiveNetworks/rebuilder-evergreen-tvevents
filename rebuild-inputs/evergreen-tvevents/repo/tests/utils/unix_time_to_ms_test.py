# pylint: disable=E0401,W0621,R0801
from app.utils import unix_time_to_ms


def test_unix_time_to_ms_positive_int():
    """
    Test unix_time_to_ms with a positive integer timestamp.
    """
    assert (
        unix_time_to_ms(1609459200) == 1609459200000
    )  # 2021-01-01 00:00:00 UTC in seconds to milliseconds


def test_unix_time_to_ms_zero():
    """
    Test unix_time_to_ms with zero timestamp.
    """
    assert unix_time_to_ms(0) == 0  # Unix epoch start


def test_unix_time_to_ms_negative_int():
    """
    Test unix_time_to_ms with a negative integer timestamp.
    """
    assert unix_time_to_ms(-1234567890) == -1234567890000  # Negative timestamp


def test_unix_time_to_ms_large_int():
    """
    Test unix_time_to_ms with a large integer timestamp.
    """
    assert unix_time_to_ms(9999999999) == 9999999999000  # Large timestamp


def test_unix_time_to_ms_float():
    """
    Test unix_time_to_ms with a float timestamp.
    """
    assert unix_time_to_ms(1609459200.123) == 1609459200123  # Float timestamp


def test_unix_time_to_ms_negative_float():
    """
    Test unix_time_to_ms with a negative float timestamp.
    """
    assert (
        unix_time_to_ms(-1234567890.789) == -1234567890789
    )  # Negative float timestamp
