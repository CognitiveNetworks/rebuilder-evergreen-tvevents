"""Tests for tvevents.domain.obfuscation module."""


class TestIsBlacklistedChannel:
    """Tests for is_blacklisted_channel."""

    def test_blacklisted_channel(self) -> None:
        from tvevents.domain.obfuscation import is_blacklisted_channel

        assert is_blacklisted_channel("12345", ["12345", "67890"]) is True

    def test_non_blacklisted_channel(self) -> None:
        from tvevents.domain.obfuscation import is_blacklisted_channel

        assert is_blacklisted_channel("99999", ["12345", "67890"]) is False

    def test_none_channel(self) -> None:
        from tvevents.domain.obfuscation import is_blacklisted_channel

        assert is_blacklisted_channel(None, ["12345"]) is False

    def test_integer_channel_id_cast_to_string(self) -> None:
        from tvevents.domain.obfuscation import is_blacklisted_channel

        assert is_blacklisted_channel(12345, ["12345"]) is True

    def test_empty_blacklist(self) -> None:
        from tvevents.domain.obfuscation import is_blacklisted_channel

        assert is_blacklisted_channel("12345", []) is False


class TestShouldObfuscateChannel:
    """Tests for should_obfuscate_channel."""

    def test_content_blocked_true(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channelid": "99999", "iscontentblocked": True}
        assert should_obfuscate_channel(output, []) is True

    def test_content_blocked_string_true(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channelid": "99999", "iscontentblocked": "true"}
        assert should_obfuscate_channel(output, []) is True

    def test_content_blocked_string_false(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channelid": "99999", "iscontentblocked": "false"}
        assert should_obfuscate_channel(output, []) is False

    def test_blacklisted_channel(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channelid": "12345", "iscontentblocked": False}
        assert should_obfuscate_channel(output, ["12345"]) is True

    def test_not_blocked_not_blacklisted(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channelid": "99999", "iscontentblocked": False}
        assert should_obfuscate_channel(output, ["12345"]) is False

    def test_flattened_channeldata_channelid_blacklisted(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channeldata_channelid": "12345", "iscontentblocked": False}
        assert should_obfuscate_channel(output, ["12345"]) is True

    def test_flattened_channeldata_channelid_not_blacklisted(self) -> None:
        from tvevents.domain.obfuscation import should_obfuscate_channel

        output = {"channeldata_channelid": "99999", "iscontentblocked": False}
        assert should_obfuscate_channel(output, ["12345"]) is False


class TestObfuscateOutput:
    """Tests for obfuscate_output."""

    def test_fields_obfuscated(self) -> None:
        from tvevents.domain.obfuscation import OBFUSCATED_STR, obfuscate_output

        output = {
            "channelid": "12345",
            "programid": "PROG1",
            "channelname": "ESPN",
            "tvid": "device-001",
        }
        result = obfuscate_output(output)
        assert result["channelid"] == OBFUSCATED_STR
        assert result["programid"] == OBFUSCATED_STR
        assert result["channelname"] == OBFUSCATED_STR
        assert result["tvid"] == "device-001"

    def test_flattened_fields_obfuscated(self) -> None:
        from tvevents.domain.obfuscation import OBFUSCATED_STR, obfuscate_output

        output = {
            "channeldata_channelid": "12345",
            "programdata_programid": "PROG1",
            "channeldata_channelname": "ESPN",
            "tvid": "device-001",
        }
        result = obfuscate_output(output)
        assert result["channeldata_channelid"] == OBFUSCATED_STR
        assert result["programdata_programid"] == OBFUSCATED_STR
        assert result["channeldata_channelname"] == OBFUSCATED_STR
        assert result["tvid"] == "device-001"
