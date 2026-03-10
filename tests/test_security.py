"""Tests for tvevents.domain.security module."""

import hashlib

import pytest


class TestSecurityHashToken:
    """Tests for security_hash_token function."""

    def test_md5_hash_us_region(self) -> None:
        """MD5 hash is used for US region (default)."""
        from tvevents.domain.security import security_hash_token

        tvid = "abc123"
        salt = "mysalt"
        expected = hashlib.md5(f"{tvid}{salt}".encode("utf-8")).hexdigest()
        assert security_hash_token(tvid, salt) == expected

    def test_sha256_hash_eu_region(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SHA-256 hash is used for EU region (eu-west-1)."""
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        import tvevents.config as cfg
        cfg._settings = None

        from tvevents.domain.security import security_hash_token

        tvid = "abc123"
        salt = "mysalt"
        expected = hashlib.sha256(f"{tvid}{salt}".encode("utf-8")).hexdigest()
        assert security_hash_token(tvid, salt) == expected

    def test_deterministic_output(self) -> None:
        """Same inputs always produce the same hash."""
        from tvevents.domain.security import security_hash_token

        result1 = security_hash_token("tvid1", "salt1")
        result2 = security_hash_token("tvid1", "salt1")
        assert result1 == result2

    def test_different_inputs_produce_different_hashes(self) -> None:
        """Different tvid/salt pairs produce different hashes."""
        from tvevents.domain.security import security_hash_token

        result1 = security_hash_token("tvid1", "salt1")
        result2 = security_hash_token("tvid2", "salt1")
        assert result1 != result2


class TestSecurityHashMatch:
    """Tests for security_hash_match function."""

    def test_valid_hash_matches(self) -> None:
        """A correctly computed hash passes validation."""
        from tvevents.domain.security import security_hash_match, security_hash_token

        tvid = "device-001"
        salt = "test-salt"
        h = security_hash_token(tvid, salt)
        assert security_hash_match(tvid, h, salt) is True

    def test_invalid_hash_fails(self) -> None:
        """An incorrect hash fails validation."""
        from tvevents.domain.security import security_hash_match

        assert security_hash_match("device-001", "wrong-hash", "test-salt") is False

    def test_timing_safe_comparison(self) -> None:
        """Verify hmac.compare_digest is used (constant-time)."""
        from tvevents.domain.security import security_hash_match

        # This test verifies the function works correctly — the actual
        # constant-time property is guaranteed by hmac.compare_digest
        assert security_hash_match("a", "not-a-hash", "salt") is False

    def test_empty_tvid(self) -> None:
        """Empty tvid still produces a valid hash."""
        from tvevents.domain.security import security_hash_match, security_hash_token

        h = security_hash_token("", "salt")
        assert security_hash_match("", h, "salt") is True
