# pylint: disable=E0401,W0621,R0801
import pytest
from app.utils import validate_request, TvEventsSecurityValidationError


def test_validate_request_valid_native_app_event():
    """
    Test validate_request with a valid NativeAppTelemetryEventType payload.
    """
    url_params = {'tvid': '12345', 'event_type': 'NATIVEAPP_TELEMETRY'}
    payload = {
        'TvEvent': {
            'tvid': '12345',
            'EventType': 'NATIVEAPP_TELEMETRY',
            'timestamp': 1617181723,
            'h': '65216148e93376cfb7f2eb53b1640dff',
            'client': 'valid_client',
        },
        'EventData': {'Timestamp': 1617181723},
    }
    assert validate_request(url_params, payload) is True


def test_validate_request_invalid_hash():
    """
    Test validate_request with an invalid security hash.
    """

    url_params = {'tvid': '12345', 'event_type': 'NATIVEAPP_TELEMETRY'}
    payload = {
        'TvEvent': {
            'tvid': '12345',
            'EventType': 'NATIVEAPP_TELEMETRY',
            'timestamp': 1617181723,
            'h': 'invalid_hash',
            'client': 'valid_client',
        },
        'EventData': {'Timestamp': 1617181723},
    }

    with pytest.raises(TvEventsSecurityValidationError):
        validate_request(url_params, payload)


def test_validate_request_no_event_type_mapping():
    """
    Test validate_request with no event type mapping.
    """
    url_params = {'tvid': '12345', 'event_type': 'UNKNOWN_EVENT_TYPE'}
    payload = {
        'TvEvent': {
            'tvid': '12345',
            'EventType': 'UNKNOWN_EVENT_TYPE',
            'timestamp': 1617181723,
            'h': '65216148e93376cfb7f2eb53b1640dff',
            'client': 'valid_client',
        },
        'EventData': {'Timestamp': 1617181723},
    }

    assert validate_request(url_params, payload) is True


def test_validate_request_invalid_params():
    """
    Test validate_request with invalid params.
    """
    url_params = {'tvid': '12345', 'event_type': 'NATIVEAPP_TELEMETRY'}
    payload = {
        'TvEvent': {
            'tvid': '12345',
            'EventType': 'NATIVEAPP_TELEMETRY',
            'timestamp': 1617181723,
            'h': '85f52b02d06d0327ef6f21f97f7a2940',
            'client': 'valid_client',
        },
        'EventData': {'Timestamp': 1617181723},
    }

    with pytest.raises(Exception):
        validate_request(url_params, payload)
