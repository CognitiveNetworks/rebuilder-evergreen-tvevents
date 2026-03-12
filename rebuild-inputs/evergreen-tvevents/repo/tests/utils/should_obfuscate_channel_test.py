# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch
from app.utils import should_obfuscate_channel


@patch('app.utils.is_blacklisted_channel')
def test_should_obfuscate_channel_content_blocked(mock_is_blacklisted_channel):
    """
    Test should_obfuscate_channel when content is blocked.
    Ensures that the function returns True.
    """
    output_json = {'iscontentblocked': True, 'channelid': '123'}
    assert should_obfuscate_channel(output_json) is True
    mock_is_blacklisted_channel.assert_not_called()


@patch('app.utils.is_blacklisted_channel')
def test_should_obfuscate_channel_content_blocked_str(mock_is_blacklisted_channel):
    """
    Test should_obfuscate_channel when content is blocked with string value.
    Ensures that the function returns True.
    """
    output_json = {'iscontentblocked': 'true', 'channelid': '123'}
    assert should_obfuscate_channel(output_json) is True
    mock_is_blacklisted_channel.assert_not_called()


@patch('app.utils.is_blacklisted_channel')
def test_should_obfuscate_channel_not_content_blocked(mock_is_blacklisted_channel):
    """
    Test should_obfuscate_channel when content is not blocked.
    Ensures that the function returns the result of is_blacklisted_channel.
    """
    output_json = {'iscontentblocked': False, 'channelid': '123'}
    mock_is_blacklisted_channel.return_value = True
    assert should_obfuscate_channel(output_json) is True
    mock_is_blacklisted_channel.assert_called_with('123')


@patch('app.utils.is_blacklisted_channel')
def test_should_obfuscate_channel_not_content_blocked_str(mock_is_blacklisted_channel):
    """
    Test should_obfuscate_channel when content is not blocked with string value.
    Ensures that the function returns the result of is_blacklisted_channel.
    """
    output_json = {'iscontentblocked': 'false', 'channelid': '123'}
    mock_is_blacklisted_channel.return_value = True
    assert should_obfuscate_channel(output_json) is True
    mock_is_blacklisted_channel.assert_called_with('123')


@patch('app.utils.is_blacklisted_channel')
def test_should_obfuscate_channel_channel_not_blacklisted(mock_is_blacklisted_channel):
    """
    Test should_obfuscate_channel when content is not blocked and channel is not blacklisted.
    Ensures that the function returns False.
    """
    output_json = {'iscontentblocked': False, 'channelid': '123'}
    mock_is_blacklisted_channel.return_value = False
    assert should_obfuscate_channel(output_json) is False
    mock_is_blacklisted_channel.assert_called_with('123')


@patch('app.utils.is_blacklisted_channel')
def test_should_obfuscate_channel_no_channel_id(mock_is_blacklisted_channel):
    """
    Test should_obfuscate_channel when there is no channel ID.
    Ensures that the function returns False.
    """
    output_json = {'iscontentblocked': False}
    mock_is_blacklisted_channel.return_value = False
    assert should_obfuscate_channel(output_json) is False
    mock_is_blacklisted_channel.assert_called_with(None)
