"""Tests for app.blacklist module."""

import json
import os

import pytest

from app.blacklist import BlacklistCache


@pytest.fixture
def cache_dir(tmp_path):
    """Provide a temp directory for cache files."""
    return str(tmp_path / "blacklist_cache")


@pytest.fixture
def cache(cache_dir):
    """Create a fresh BlacklistCache with temp file path."""
    c = BlacklistCache()
    c.cache_filepath = cache_dir
    c._channel_ids = []
    c._last_refresh = 0.0
    return c


class TestBlacklistCacheInit:
    def test_default_filepath(self):
        c = BlacklistCache()
        assert c.cache_filepath is not None

    def test_entry_count_starts_zero(self, cache):
        assert cache.entry_count == 0


class TestBlacklistCacheReadWrite:
    def test_write_and_read_cache(self, cache, cache_dir):
        ids = ["ch-001", "ch-002", "ch-003"]
        cache._write_cache(ids)

        # Verify file was written
        assert os.path.exists(cache_dir)

        # Read back
        result = cache._read_cache()
        assert result is not None
        assert len(result) == 3

    def test_read_missing_file_returns_none(self, cache):
        cache.cache_filepath = "/tmp/nonexistent_test_cache_file"  # noqa: S108
        result = cache._read_cache()
        assert result is None


class TestBlacklistCacheRefresh:
    def test_refresh_from_rds(self, cache, mock_rds_module):
        mock_rds_module.execute_query.return_value = [
            {"channel_id": "ch-100"},
            {"channel_id": "ch-200"},
        ]
        result = cache.refresh()
        assert result is True
        assert cache.entry_count == 2

    def test_refresh_rds_failure_returns_false(self, cache, mock_rds_module):
        mock_rds_module.execute_query.side_effect = Exception("RDS down")
        result = cache.refresh()
        assert result is False


class TestBlacklistCacheGetChannelIds:
    def test_returns_memory_cache(self, cache):
        cache._channel_ids = ["ch-001", "ch-002"]
        result = cache.get_channel_ids()
        assert result == ["ch-001", "ch-002"]

    def test_falls_back_to_file(self, cache, cache_dir):
        # Write file cache manually
        with open(cache_dir, "w") as f:
            json.dump(["ch-file-1", "ch-file-2"], f)

        cache._channel_ids = None  # No memory cache triggers file fallback
        result = cache.get_channel_ids()
        assert len(result) == 2

    def test_falls_back_to_rds(self, cache, mock_rds_module):
        cache._channel_ids = None
        cache.cache_filepath = "/tmp/nonexistent_test_cache_path"  # noqa: S108
        mock_rds_module.execute_query.return_value = [{"channel_id": "ch-rds-1"}]
        result = cache.get_channel_ids()
        assert "ch-rds-1" in result


class TestBlacklistCacheIsBlacklisted:
    def test_blacklisted_channel(self, cache):
        cache._channel_ids = ["ch-blocked"]
        assert cache.is_blacklisted("ch-blocked") is True

    def test_non_blacklisted_channel(self, cache):
        cache._channel_ids = ["ch-blocked"]
        assert cache.is_blacklisted("ch-ok") is False


class TestBlacklistCacheInitialize:
    def test_initialize_success(self, cache, mock_rds_module):
        mock_rds_module.execute_query.return_value = [
            {"channel_id": "ch-init-1"},
        ]
        cache.initialize()
        assert cache.entry_count == 1

    def test_initialize_falls_back_to_file(self, cache, mock_rds_module, cache_dir):
        # Write file cache
        with open(cache_dir, "w") as f:
            json.dump(["ch-fallback-1"], f)

        mock_rds_module.execute_query.side_effect = Exception("RDS down")
        cache.initialize()
        assert cache.entry_count == 1
