"""Channel obfuscation tests — blacklist detection, iscontentblocked
handling, and field masking.

Verifies that the obfuscation pipeline correctly identifies channels
requiring censorship and replaces channelid/programid/channelname
with 'OBFUSCATED'.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from tvevents.domain.obfuscation import (
    OBFUSCATED_STR,
    obfuscate_output,
    should_obfuscate_channel,
)


def _make_blacklist_checker(blacklisted: set[str]) -> AsyncMock:
    """Create a mock BlacklistChecker that knows a given set of channel IDs."""
    checker = AsyncMock()
    checker.is_blacklisted = AsyncMock(side_effect=lambda cid: cid in blacklisted)
    return checker


class TestChannelObfuscation:
    """Validate obfuscation rules: blacklisted channels, iscontentblocked
    flag (bool and string), and the three field replacement."""

    @pytest.mark.asyncio
    async def test_blacklisted_channel_obfuscated(self) -> None:
        """TV tunes to channel 10501 which is in the blacklist →
        should_obfuscate_channel returns True."""
        checker = _make_blacklist_checker({"10501", "99999"})
        output: dict[str, Any] = {
            "channelid": "10501",
            "iscontentblocked": False,
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is True

    @pytest.mark.asyncio
    async def test_non_blacklisted_channel_not_obfuscated(self) -> None:
        """TV tunes to channel 12345 which is NOT in the blacklist →
        should_obfuscate_channel returns False."""
        checker = _make_blacklist_checker({"10501", "99999"})
        output: dict[str, Any] = {
            "channelid": "12345",
            "iscontentblocked": False,
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is False

    @pytest.mark.asyncio
    async def test_iscontentblocked_true_triggers_obfuscation(self) -> None:
        """iscontentblocked=True forces obfuscation even when the channel
        12345 is not in the blacklist."""
        checker = _make_blacklist_checker(set())
        output: dict[str, Any] = {
            "channelid": "12345",
            "iscontentblocked": True,
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is True

    @pytest.mark.asyncio
    async def test_iscontentblocked_string_true_triggers_obfuscation(self) -> None:
        """Legacy quirk: iscontentblocked='true' (string) is treated as
        truthy → obfuscation triggered."""
        checker = _make_blacklist_checker(set())
        output: dict[str, Any] = {
            "channelid": "12345",
            "iscontentblocked": "true",
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is True

    @pytest.mark.asyncio
    async def test_iscontentblocked_string_false_no_obfuscation(self) -> None:
        """iscontentblocked='false' (string) is treated as falsy → no
        obfuscation when channel is not blacklisted."""
        checker = _make_blacklist_checker(set())
        output: dict[str, Any] = {
            "channelid": "12345",
            "iscontentblocked": "false",
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is False

    @pytest.mark.asyncio
    async def test_null_channelid_not_blacklisted(self) -> None:
        """channelid=None with iscontentblocked=False → returns False
        (None is not in any blacklist)."""
        checker = _make_blacklist_checker({"10501"})
        output: dict[str, Any] = {
            "channelid": None,
            "iscontentblocked": False,
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is False

    def test_obfuscate_output_replaces_three_fields(self) -> None:
        """obfuscate_output mutates channelid, programid, channelname
        to 'OBFUSCATED' in place."""
        output: dict[str, Any] = {
            "channelid": "10045",
            "programid": "EP012345678901",
            "channelname": "PBS",
            "tvid": "ITV00C000000000000001",
        }
        result = obfuscate_output(output)
        assert result["channelid"] == OBFUSCATED_STR
        assert result["programid"] == OBFUSCATED_STR
        assert result["channelname"] == OBFUSCATED_STR
        # Other fields untouched
        assert result["tvid"] == "ITV00C000000000000001"

    @pytest.mark.asyncio
    async def test_integer_channelid_converted_to_string_for_lookup(self) -> None:
        """Channel ID may be an integer in the payload — str(channelid)
        is used for the blacklist membership check."""
        checker = _make_blacklist_checker({"10501"})
        output: dict[str, Any] = {
            "channelid": 10501,  # integer, not string
            "iscontentblocked": False,
        }
        result = await should_obfuscate_channel(output, checker)
        assert result is True
