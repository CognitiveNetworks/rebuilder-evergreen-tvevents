# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch
from app.utils import is_blacklisted_channel


@patch('app.utils.TVEVENTS_RDS')
def test_is_blacklisted_channel_blacklisted(mock_tvevents_rds):
    """
    Test is_blacklisted_channel with a blacklisted channel ID.
    Ensures that the function returns True.
    """
    mock_tvevents_rds.blacklisted_channel_ids.return_value = ['123', '456']
    channelid = '123'
    assert is_blacklisted_channel(channelid) is True


@patch('app.utils.TVEVENTS_RDS')
def test_is_blacklisted_channel_not_blacklisted(mock_tvevents_rds):
    """
    Test is_blacklisted_channel with a non-blacklisted channel ID.
    Ensures that the function returns False.
    """
    mock_tvevents_rds.blacklisted_channel_ids.return_value = ['123', '456']
    channelid = '789'
    assert is_blacklisted_channel(channelid) is False


@patch('app.utils.LOGGER')
def test_is_blacklisted_channel_none(mock_logger):
    """
    Test is_blacklisted_channel with None as channel ID.
    Ensures that the function returns False.
    """
    channelid = None
    assert is_blacklisted_channel(channelid) is False
    mock_logger.debug.assert_not_called()
