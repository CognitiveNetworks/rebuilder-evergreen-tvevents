"""Channel obfuscation logic."""

from app import configure_logging
from app.blacklist import blacklist_cache

LOGGER = configure_logging()

OBFUSCATED_STR = "OBFUSCATED"


def should_obfuscate_channel(output_json: dict) -> bool:
    """
    Determines if channel info should be obfuscated.

    Obfuscation triggered when iscontentblocked is True or channel is blacklisted.
    """
    channel_id = output_json.get("channelid")
    is_content_blocked = output_json.get("iscontentblocked", False)

    # Handles scenario where payload value is str instead of bool
    if isinstance(is_content_blocked, str):
        is_content_blocked = is_content_blocked.lower() == "true"

    LOGGER.debug(
        "should_obfuscate_channel: iscontentblocked=%s; channelid=%s",
        is_content_blocked,
        channel_id,
    )
    return True if is_content_blocked else blacklist_cache.is_blacklisted(channel_id)


def obfuscate_channel_fields(output_json: dict) -> dict:
    """Replace channel-identifying fields with obfuscated values."""
    output_json["channelid"] = OBFUSCATED_STR
    output_json["programid"] = OBFUSCATED_STR
    output_json["channelname"] = OBFUSCATED_STR
    return output_json
