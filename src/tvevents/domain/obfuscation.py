"""Channel blacklist obfuscation — ported from legacy app/utils.py."""


import logging
from typing import Any

logger = logging.getLogger(__name__)

OBFUSCATED_STR = "OBFUSCATED"


def is_blacklisted_channel(
    channelid: Any, blacklisted_ids: list[str]
) -> bool:
    """Check if a channel ID is in the blacklisted set."""
    if channelid is None:
        return False
    logger.debug("Checking if channel is blacklisted: %s", channelid)
    return str(channelid) in blacklisted_ids


def should_obfuscate_channel(
    output_json: dict[str, Any], blacklisted_ids: list[str]
) -> bool:
    """Determine if channel info should be obfuscated.

    Returns True if isContentBlocked is true OR the channel is blacklisted.
    """
    channel_id = output_json.get("channelid") or output_json.get("channeldata_channelid")
    is_content_blocked: Any = output_json.get("iscontentblocked", False)

    if isinstance(is_content_blocked, str):
        is_content_blocked = is_content_blocked.lower() == "true"

    logger.debug(
        "should_obfuscate_channel: iscontentblocked=%s; channelid=%s",
        is_content_blocked,
        channel_id,
    )
    if is_content_blocked:
        return True
    return is_blacklisted_channel(channel_id, blacklisted_ids)


def obfuscate_output(output_json: dict[str, Any]) -> dict[str, Any]:
    """Replace channel fields with OBFUSCATED string."""
    for key in ("channelid", "channeldata_channelid"):
        if key in output_json:
            output_json[key] = OBFUSCATED_STR
    for key in ("programid", "programdata_programid"):
        if key in output_json:
            output_json[key] = OBFUSCATED_STR
    for key in ("channelname", "channeldata_channelname"):
        if key in output_json:
            output_json[key] = OBFUSCATED_STR
    return output_json
