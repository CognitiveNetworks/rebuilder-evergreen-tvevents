"""HMAC-based request validation — replaces cnlib.token_hash."""


import hashlib
import hmac
import logging

from tvevents.config import get_settings

logger = logging.getLogger(__name__)


def security_hash_token(tvid: str, salt: str) -> str:
    """Compute the security hash for a given tvid and salt.

    Uses SHA-256 for EU region (eu-west-1), MD5 otherwise.
    Matches legacy cnlib.token_hash.security_hash_token behavior.
    """
    settings = get_settings()
    region = settings.aws_region

    raw = f"{tvid}{salt}"

    if region == "eu-west-1":
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324


def security_hash_match(tvid: str, h_value: str, salt: str) -> bool:
    """Verify the security hash using constant-time comparison.

    Fixes legacy timing attack vulnerability (cnlib used ==).
    """
    expected = security_hash_token(tvid, salt)
    return hmac.compare_digest(expected, h_value)
