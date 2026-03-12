"""Tests for app.obfuscation module."""

from app.obfuscation import (
    OBFUSCATED_STR,
    obfuscate_channel_fields,
    should_obfuscate_channel,
)


class TestShouldObfuscateChannel:
    def test_returns_true_when_content_blocked(self):
        output = {"iscontentblocked": True}
        assert should_obfuscate_channel(output) is True

    def test_returns_true_when_content_blocked_string(self):
        output = {"iscontentblocked": "True"}
        assert should_obfuscate_channel(output) is True

    def test_returns_false_when_not_blocked(self):
        output = {"iscontentblocked": False}
        assert should_obfuscate_channel(output) is False

    def test_returns_true_when_blacklisted(self):
        """Test with a blacklisted channel ID."""
        from unittest.mock import MagicMock, patch

        mock_cache = MagicMock()
        mock_cache.is_blacklisted.return_value = True

        with patch("app.obfuscation.blacklist_cache", mock_cache):
            output = {"iscontentblocked": False, "tvevent_channelid": "ch-blocked"}
            assert should_obfuscate_channel(output) is True

    def test_returns_false_when_not_blacklisted(self):
        from unittest.mock import MagicMock, patch

        mock_cache = MagicMock()
        mock_cache.is_blacklisted.return_value = False

        with patch("app.obfuscation.blacklist_cache", mock_cache):
            output = {"iscontentblocked": False, "tvevent_channelid": "ch-ok"}
            assert should_obfuscate_channel(output) is False


class TestObfuscateChannelFields:
    def test_obfuscates_fields(self):
        output = {
            "channelid": "ch-001",
            "programid": "prog-001",
            "channelname": "ESPN",
            "other_field": "untouched",
        }
        result = obfuscate_channel_fields(output)
        assert result["channelid"] == OBFUSCATED_STR
        assert result["programid"] == OBFUSCATED_STR
        assert result["channelname"] == OBFUSCATED_STR
        assert result["other_field"] == "untouched"

    def test_handles_missing_fields(self):
        output = {"other_field": "untouched"}
        result = obfuscate_channel_fields(output)
        assert result["other_field"] == "untouched"
