# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch
from app.utils import push_changes_to_firehose


@patch('app.utils.LOGGER')
@patch('app.utils.TVEVENTS_RDS')
@patch('app.utils.send_to_valid_firehoses')
def test_push_changes_to_firehose_valid_payload(
    mock_send_to_valid_firehoses, mock_tvevents_rds, mock_logger
):
    """
    Test push_changes_to_firehose with valid payload.
    Ensures that the function processes and sends the data to firehose.
    """
    payload = {
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
        },
    }

    mock_tvevents_rds.blacklisted_channel_ids.return_value = ['123', '456']

    push_changes_to_firehose(payload)

    mock_logger.debug.assert_any_call('TVEVENTS_DEBUG is: %s', False)
    mock_send_to_valid_firehoses.assert_called()


@patch('app.utils.LOGGER')
@patch('app.utils.send_to_valid_firehoses')
def test_push_changes_to_firehose_obfuscate_channel(
    mock_send_to_valid_firehoses, mock_logger
):
    """
    Test push_changes_to_firehose when channel information needs to be obfuscated.
    Ensures that the function obfuscates the channel information and sends the data to firehose.
    """
    payload = {
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
            "IsContentBlocked": True,
        },
    }

    push_changes_to_firehose(payload)

    mock_logger.debug.assert_any_call('TVEVENTS_DEBUG is: %s', False)

    mock_logger.debug.assert_any_call(
        'Obfuscating: tvid=2180993, channel_id={ch_id}, iscontentblocked={blocked}'.format(
            ch_id='abc123',
            blocked=True,
        )
    )

    mock_send_to_valid_firehoses.assert_called()
