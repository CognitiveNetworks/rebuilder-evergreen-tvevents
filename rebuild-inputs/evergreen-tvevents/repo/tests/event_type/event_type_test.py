# pylint: disable=E0401,W0621,R0801
import pytest
from app.event_type import EventType


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


def test_event_type_init(valid_payload):
    """
    Test the initialization of EventType.
    Ensures that the attributes are set correctly.
    """
    event_type = EventType(valid_payload)
    assert event_type.payload == valid_payload
    assert event_type.event_type == "NATIVEAPP_TELEMETRY"
    assert event_type.tvid == "2180993"
    assert event_type.event_data_params == valid_payload['EventData']


def test_validate_event_type_payload(valid_payload):
    """
    Test the validate_event_type_payload method is passed
    """
    event_type = EventType(valid_payload)
    assert event_type.validate_event_type_payload() is None


def test_generate_event_data_output_json(valid_payload):
    """
    Test the generate_event_data_output_json method is passed.
    """
    event_type = EventType(valid_payload)

    assert event_type.generate_event_data_output_json() is None
