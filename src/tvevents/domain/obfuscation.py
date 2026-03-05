"""Channel obfuscation — blacklist detection and content masking.

Preserves the exact legacy ``should_obfuscate_channel`` and obfuscation
logic from ``utils.py``.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

OBFUSCATED_STR: str = "OBFUSCATED"


class BlacklistChecker(Protocol):
    """Callable that checks if a channel ID is blacklisted."""

    async def is_blacklisted(self, channel_id: str) -> bool: ...


async def should_obfuscate_channel(
    output_json: dict[str, Any],
    blacklist_checker: BlacklistChecker,
) -> bool:
    """Determine if channel info should be obfuscated.

    Returns ``True`` when ``iscontentblocked`` is truthy **or** the
    ``channelid`` appears in the blacklist.  Handles the legacy quirk where
    ``iscontentblocked`` may be the *string* ``"true"`` instead of a bool.
    """
    channel_id: Any = output_json.get("channelid")
    is_content_blocked: Any = output_json.get("iscontentblocked", False)

    # Legacy: payload may encode booleans as strings
    if isinstance(is_content_blocked, str):
        is_content_blocked = is_content_blocked.lower() == "true"

    logger.debug(
        "should_obfuscate_channel: iscontentblocked=%s; channelid=%s",
        is_content_blocked,
        channel_id,
    )

    if is_content_blocked:
        return True

    # channelid value is optional
    if channel_id is None:
        return False

    return await blacklist_checker.is_blacklisted(str(channel_id))


def obfuscate_output(output_json: dict[str, Any]) -> dict[str, Any]:
    """Replace channel/program fields with ``"OBFUSCATED"``.

    Mutates *output_json* **in place** and returns it for convenience.
    """
    output_json["channelid"] = OBFUSCATED_STR
    output_json["programid"] = OBFUSCATED_STR
    output_json["channelname"] = OBFUSCATED_STR
    return output_json
