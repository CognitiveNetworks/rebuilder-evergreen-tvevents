# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch
import pytest
from app.utils import generate_output_json


@patch('app.utils.LOGGER')
def test_generate_output_json_valid(mock_logger):
    """
    Test generate_output_json with valid input payload.
    Ensures that the function returns the correct flattened JSON output.
    """
    request_json = {
        'TvEvent': {
            'tvid': '12345',
            'EventType': 'NATIVEAPP_TELEMETRY',
            'timestamp': 1617181723,
            'h': '65216148e93376cfb7f2eb53b1640dff',
            'client': 'valid_client',
        },
        'EventData': {
            'NameSpace': 0,
            'AppId': "test_appid",
            'AppName': "test+",
            'Timestamp': 1617181723,
        },
    }

    expected_output = {
        'appid': 'test_appid',
        'appname': 'test+',
        'namespace': 0,
        'client': 'valid_client',
        'eventdata_timestamp': 1617181723,
        'tvevent_eventtype': 'NATIVEAPP_TELEMETRY',
        'tvevent_timestamp': 1617181723,
        'tvid': '12345',
        'zoo': 'local-testing',
    }

    assert generate_output_json(request_json) == expected_output
    mock_logger.error.assert_not_called()


@patch('app.utils.LOGGER')
def test_generate_output_json_missing_key(mock_logger):
    """
    Test generate_output_json with missing key in input payload.
    Ensures that the function raises a KeyError and logs an error message.
    """
    request_json = {
        'TvEvent': {
            'EventType': 'TEST_EVENT',
            'timestamp': 1234567890,
            'key1': 'value1',
        }
    }

    with pytest.raises(KeyError):
        generate_output_json(request_json)

    mock_logger.error.assert_called_once_with(
        'generate_output failed: Missing \'EventData\', {request_json}'.format(
            request_json=request_json
        )
    )


@patch('app.utils.LOGGER')
def test_generate_output_json_no_event_type_mapping(mock_logger):
    """
    Test generate_output_json with no event type mapping.
    Ensures that the function returns the flattened EventData.
    """
    request_json = {
        'TvEvent': {
            'tvid': '12345',
            'EventType': 'NO_MAPPING_EVENT',
            'timestamp': 1617181723,
            'h': '65216148e93376cfb7f2eb53b1640dff',
            'client': 'valid_client',
        },
        'EventData': {'Timestamp': 1617181723},
    }

    expected_output = {
        'client': 'valid_client',
        'timestamp': 1617181723,
        'tvevent_eventtype': 'NO_MAPPING_EVENT',
        'tvevent_timestamp': 1617181723,
        'tvid': '12345',
        'zoo': 'local-testing',
    }

    assert generate_output_json(request_json) == expected_output
    mock_logger.error.assert_not_called()


@patch('app.utils.LOGGER')
def test_generate_output_json_unhandled_exception(mock_logger):
    """
    Test generate_output_json with an unhandled exception.
    Ensures that the function raises the exception and logs an error message.
    """
    request_json = {"some_garbage"}

    with pytest.raises(Exception):
        generate_output_json(request_json)

    mock_logger.error.assert_called_once_with(
        'Unhandled exception in generate_output: \'set\' object is not subscriptable'
    )
