# pylint: disable=E0401,W0621,R0801
import pytest
from app.utils import TvEventsMissingRequiredParamError, TvEventsInvalidPayloadError
from app.event_type import PlatformTelemetryEventType


@pytest.fixture
def valid_payload():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "NATIVEAPP_TELEMETRY",
        },
        "EventData": {
            "AppId": "123abc",
            "AppName": "WatchFree+",
            "Timestamp": 1599860922440,
            "EventType": "ChannelChange",
            "AdId": {
                "LMT": 0,
                "IFA": "aa84c930-asdf-asdf-8cc0-123b55b2ff07",
                "IFA_TYPE": "dpid",
            },
            "ChannelId": "abc123",
            "ProgramId": "x9y8x7",
            "WatchFreePlusSessionId": "68b429c2-347b-4075-98a9-6d18d237cf68",
            "ChannelName": "Newsy",
            "NameSpace": 4,
            "Environment": "LOCAL",
            "IsContentBlocked": False,
            "PanelData": {
                "Timestamp": 1599860922441,
                "PanelState": 'ON',
                "WakeupReason": 0,
            },
        },
    }


@pytest.fixture
def invalid_payload_missing_required():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "NATIVEAPP_TELEMETRY",
        },
        "EventData": {
            "AppId": "123abc",
            "AppName": "WatchFree+",
            "Timestamp": 1599860922440,
            "EventType": "ChannelChange",
            "AdId": {
                "LMT": 0,
                "IFA": "aa84c930-asdf-asdf-8cc0-123b55b2ff07",
                "IFA_TYPE": "dpid",
            },
            "ChannelId": "abc123",
            "ProgramId": "x9y8x7",
            "WatchFreePlusSessionId": "68b429c2-347b-4075-98a9-6d18d237cf68",
            "ChannelName": "Newsy",
            "NameSpace": 4,
            "Environment": "LOCAL",
            "IsContentBlocked": False,
            "PanelData": {"Timestamp": 1599860922441, "PanelState": 'ON'},
        },
    }


@pytest.fixture
def invalid_payload_invalid_value():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "NATIVEAPP_TELEMETRY",
        },
        "EventData": {
            "AppId": "123abc",
            "AppName": "WatchFree+",
            "Timestamp": 1599860922440,
            "EventType": "ChannelChange",
            "AdId": {
                "LMT": 0,
                "IFA": "aa84c930-asdf-asdf-8cc0-123b55b2ff07",
                "IFA_TYPE": "dpid",
            },
            "ChannelId": "abc123",
            "ProgramId": "x9y8x7",
            "WatchFreePlusSessionId": "68b429c2-347b-4075-98a9-6d18d237cf68",
            "ChannelName": "Newsy",
            "NameSpace": 4,
            "Environment": "LOCAL",
            "IsContentBlocked": False,
            "PanelData": {
                "Timestamp": 1599860922441,
                "PanelState": 'INVALID',
                "WakeupReason": 0,
            },
        },
    }


def test_validate_event_type_payload_valid(valid_payload):
    """
    Test validate_event_type_payload with a valid payload.
    Ensures that the payload is validated and returns True.
    """
    event_type = PlatformTelemetryEventType(valid_payload)
    assert event_type.validate_event_type_payload() is True


def test_validate_event_type_payload_missing_required(invalid_payload_missing_required):
    """
    Test validate_event_type_payload with a payload missing required parameters.
    Ensures that the appropriate exception is raised.
    """
    event_type = PlatformTelemetryEventType(invalid_payload_missing_required)
    with pytest.raises(TvEventsMissingRequiredParamError):
        event_type.validate_event_type_payload()


def test_validate_event_type_payload_invalid_value(invalid_payload_invalid_value):
    """
    Test validate_event_type_payload with a payload containing invalid values.
    Ensures that the appropriate exception is raised.
    """
    event_type = PlatformTelemetryEventType(invalid_payload_invalid_value)
    with pytest.raises(TvEventsInvalidPayloadError):
        event_type.validate_event_type_payload()


def test_validate_panel_data_valid(valid_payload):
    """
    Test validate_panel_data with a valid payload.
    Ensures that the panel data is validated and returns True.
    """
    event_type = PlatformTelemetryEventType(valid_payload)
    assert event_type.validate_panel_data() is True


def test_generate_event_data_output_json(valid_payload):
    """
    Test generate_event_data_output_json with a valid payload.
    Ensures that the output JSON is generated correctly.
    """
    event_type = PlatformTelemetryEventType(valid_payload)
    expected_output = {
        'adid_ifa': 'aa84c930-asdf-asdf-8cc0-123b55b2ff07',
        'adid_ifa_type': 'dpid',
        'adid_lmt': 0,
        'appid': '123abc',
        'appname': 'WatchFree+',
        'channelid': 'abc123',
        'channelname': 'Newsy',
        'environment': 'LOCAL',
        'eventtype': 'ChannelChange',
        'iscontentblocked': False,
        'namespace': 4,
        'paneldata_panelstate': 'ON',
        'paneldata_timestamp': 1599860922441,
        'paneldata_wakeupreason': 0,
        'programid': 'x9y8x7',
        'timestamp': 1599860922440,
        'watchfreeplussessionid': '68b429c2-347b-4075-98a9-6d18d237cf68',
    }
    assert event_type.generate_event_data_output_json() == expected_output
