"""JSON flattening tests — recursive flatten, key lowering, ignore keys.

Validates the flatten_request_json helper that powers the output JSON
contract for all event types.
"""

from __future__ import annotations

from typing import Any

from tvevents.domain.event_types import flatten_request_json


class TestJsonFlattening:
    """Verify that flatten_request_json produces the exact key format
    that downstream Kafka consumers depend on."""

    def test_flat_json_returns_unchanged(self) -> None:
        """A flat dict with tvid and client passes through with keys lowercased."""
        result = flatten_request_json({"tvid": "ITV00C000000000000001", "client": "smartcast"})
        assert result == {"tvid": "ITV00C000000000000001", "client": "smartcast"}

    def test_nested_json_flattened_with_prefix(self) -> None:
        """Nested dict {channelData: {majorId: 45}} flattens to
        channeldata_majorid: 45 — prefix + underscore + key, all lower."""
        result = flatten_request_json({"channelData": {"majorId": 45}})
        assert result == {"channeldata_majorid": 45}

    def test_deeply_nested_json_flattened(self) -> None:
        """Three-level nesting: the flatten function uses only the
        immediate parent key as prefix (not cumulative).  So
        {channelData: {tunerInfo: {signalStrength: 95}}} → tunerinfo_signalstrength: 95."""
        data: dict[str, Any] = {
            "channelData": {
                "tunerInfo": {
                    "signalStrength": 95,
                },
            },
        }
        result = flatten_request_json(data)
        assert result["tunerinfo_signalstrength"] == 95

    def test_keys_lowercased(self) -> None:
        """Upper-case keys are lowered: {MajorId: 45} → {majorid: 45}."""
        result = flatten_request_json({"MajorId": 45})
        assert "majorid" in result
        assert result["majorid"] == 45

    def test_keys_with_prefix_lowercased(self) -> None:
        """Key prefix and key both lowered:
        {ChannelData: {MajorId: 45}} → channeldata_majorid: 45."""
        result = flatten_request_json({"ChannelData": {"MajorId": 45}})
        assert "channeldata_majorid" in result
        assert result["channeldata_majorid"] == 45

    def test_ignore_keys_excluded(self) -> None:
        """ignore_keys=['h', 'timestamp'] causes those keys to be
        excluded from the output, matching the legacy contract."""
        data: dict[str, Any] = {
            "tvid": "ITV00C000000000000001",
            "h": "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
            "timestamp": 1709568000000,
            "client": "smartcast",
        }
        result = flatten_request_json(data, ignore_keys=["h", "timestamp"])
        assert "h" not in result
        assert "timestamp" not in result
        assert result["tvid"] == "ITV00C000000000000001"
        assert result["client"] == "smartcast"

    def test_ignore_keys_as_string_uses_substring_match(self) -> None:
        """Legacy quirk: when ignore_keys is a *string* (not a list), the
        ``in`` operator checks if the *key* is a substring of the
        ignore_keys string (``k in 'Timestamp'``).  So:
        - 'Timestamp' in 'Timestamp' → True (exact match, skipped)
        - 'T' in 'Timestamp' → True (substring, skipped)
        - 'SomeTimestamp' in 'Timestamp' → False (NOT a substring, kept)
        - 'Action' in 'Timestamp' → False (kept)
        """
        data: dict[str, Any] = {
            "Timestamp": 1709568000000,
            "Action": "launch",
            "stamp": 42,
        }
        result = flatten_request_json(data, ignore_keys="Timestamp")
        # 'Timestamp' is a substring of 'Timestamp' → skipped
        assert "timestamp" not in result
        # 'stamp' is a substring of 'Timestamp' → skipped
        assert "stamp" not in result
        # 'Action' is NOT a substring of 'Timestamp' → kept
        assert result["action"] == "launch"
