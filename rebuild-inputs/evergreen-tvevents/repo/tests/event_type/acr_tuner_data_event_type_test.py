# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch
import pytest
from app.utils import TvEventsMissingRequiredParamError, TvEventsInvalidPayloadError
from app.event_type import AcrTunerDataEventType


@pytest.fixture
def valid_heartbeat_payload():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "ACR_TUNER_DATA",
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
            "Heartbeat": {
                "channelData": {"majorId": 7, "minorId": 1},
            },
        },
    }


@pytest.fixture
def valid_payload():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "ACR_TUNER_DATA",
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
            "channelData": {"majorId": 7, "minorId": 1},
            "resolution": {"vRes": 1080, "hRes": 1920},
        },
    }


@pytest.fixture
def invalid_payload_missing_channel_data():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "ACR_TUNER_DATA",
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
            # Missing channelData
            "resolution": {"vRes": 1080, "hRes": 1920},
        },
    }


@pytest.fixture
def invalid_payload_invalid_heartbeat():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "ACR_TUNER_DATA",
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
            "Heartbeat": {
                "channelData": {"majorId": 7, "minorId": 1},
            },
            "channelData": {"majorId": 7, "minorId": 1},
        },
    }


@pytest.fixture
def invalid_payload_missing_heartbeat_params():
    return {
        "TvEvent": {
            "tvid": "2180993",
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
            "EventType": "ACR_TUNER_DATA",
        },
        "EventData": {
            "AppId": "123abc",
            "AppName": "WatchFree+",
            "Timestamp": 1599860922440,
            "EventType": "Heartbeat",
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
            "Heartbeat": {
                # Missing required heartbeat parameters (channelData or programData)
            },
        },
    }


@pytest.fixture
def payload_with_programdata_and_heartbeat():
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
            "EventType": "Heartbeat",
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
            "Heartbeat": {
                "channelData": {"majorId": 7, "minorId": 1},
            },
            "programdata_starttime": 1599860922,
        },
    }


def test_validate_event_type_payload_valid(valid_payload):
    """
    Test validate_event_type_payload with a valid payload.
    Ensures that the payload is validated and returns True.
    """
    event_type = AcrTunerDataEventType(valid_payload)
    assert event_type.validate_event_type_payload() is True


def test_validate_event_type_payload_with_heartbeat_valid(valid_heartbeat_payload):
    """
    Test validate_event_type_payload with a valid heartbeat payload.
    Ensures that the payload is validated and returns True.
    """
    event_type = AcrTunerDataEventType(valid_heartbeat_payload)
    assert event_type.validate_event_type_payload() is True


def test_validate_event_type_payload_missing_channel_data(
    invalid_payload_missing_channel_data,
):
    """
    Test validate_event_type_payload with a payload missing channelData.
    Ensures that the appropriate exception is raised.
    """
    event_type = AcrTunerDataEventType(invalid_payload_missing_channel_data)
    with pytest.raises(TvEventsMissingRequiredParamError):
        event_type.validate_event_type_payload()


def test_validate_event_type_payload_missing_heartbeat_params(
    invalid_payload_missing_heartbeat_params,
):
    """
    Test validate_event_type_payload with a payload missing required heartbeat parameters.
    Ensures that the appropriate exception is raised.
    """
    event_type = AcrTunerDataEventType(invalid_payload_missing_heartbeat_params)
    with pytest.raises(TvEventsMissingRequiredParamError):
        event_type.validate_event_type_payload()


def test_validate_event_type_payload_invalid_heartbeat(
    invalid_payload_invalid_heartbeat,
):
    """
    Test validate_event_type_payload with an invalid heartbeat payload.
    Ensures that the appropriate exception is raised.
    """
    event_type = AcrTunerDataEventType(invalid_payload_invalid_heartbeat)
    with pytest.raises(TvEventsInvalidPayloadError):
        event_type.validate_event_type_payload()


def test_validate_heartbeat_event_valid(valid_heartbeat_payload):
    """
    Test validate_heartbeat_event with a valid payload.
    Ensures that the heartbeat event is validated and returns True.
    """
    event_type = AcrTunerDataEventType(valid_heartbeat_payload)
    assert event_type.validate_heartbeat_event() is True


def test_generate_event_data_output_json(valid_payload):
    """
    Test generate_event_data_output_json with a valid payload.
    Ensures that the output JSON is generated correctly.
    """
    event_type = AcrTunerDataEventType(valid_payload)
    expected_output = {
        'adid_ifa': 'aa84c930-asdf-asdf-8cc0-123b55b2ff07',
        'adid_ifa_type': 'dpid',
        'adid_lmt': 0,
        'appid': '123abc',
        'appname': 'WatchFree+',
        'channeldata_majorid': 7,
        'channeldata_minorid': 1,
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
        'resolution_hres': 1920,
        'resolution_vres': 1080,
        'timestamp': 1599860922440,
        'watchfreeplussessionid': '68b429c2-347b-4075-98a9-6d18d237cf68',
    }
    assert event_type.generate_event_data_output_json() == expected_output


@patch('app.event_type.LOGGER')
def test_generate_event_data_output_json_with_programdata_and_heartbeat(
    mock_logger, payload_with_programdata_and_heartbeat
):
    """
    Test generate_event_data_output_json with a payload containing
    programdata_starttime and Heartbeat. Ensures that the programdata_starttime
    is converted and Heartbeat event is handled.
    """

    event_type = AcrTunerDataEventType(payload_with_programdata_and_heartbeat)
    event_data_output = event_type.generate_event_data_output_json()

    assert event_data_output['programdata_starttime'] == 1599860922000

    mock_logger.debug.assert_called_once_with(
        'Heartbeat event received for tvid=2180993'
    )
    assert event_data_output['eventtype'] == 'Heartbeat'
