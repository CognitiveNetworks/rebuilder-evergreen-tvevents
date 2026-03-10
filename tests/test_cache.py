"""Tests for tvevents.infrastructure.cache module."""

import json
import os
import tempfile

import pytest


class TestBlacklistCache:
    """Tests for BlacklistCache."""

    def test_store_and_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        try:
            monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", filepath)
            import tvevents.config as cfg
            cfg._settings = None

            cache = BlacklistCache()
            ids = ["111", "222", "333"]
            cache.store(ids)

            result = cache.read()
            assert result == ids
        finally:
            os.unlink(filepath)

    def test_read_missing_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", "/tmp/.nonexistent_test_cache")
        import tvevents.config as cfg
        cfg._settings = None

        cache = BlacklistCache()
        assert cache.read() is None

    def test_get_blacklisted_channel_ids_from_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["aaa", "bbb"], f)
            filepath = f.name

        try:
            monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", filepath)
            import tvevents.config as cfg
            cfg._settings = None

            cache = BlacklistCache()
            result = cache.get_blacklisted_channel_ids()
            assert result == ["aaa", "bbb"]
        finally:
            os.unlink(filepath)

    def test_get_blacklisted_channel_ids_fallback_to_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", "/tmp/.test_fallback_cache")
        import tvevents.config as cfg
        cfg._settings = None

        # Ensure no file exists
        try:
            os.unlink("/tmp/.test_fallback_cache")
        except FileNotFoundError:
            pass

        cache = BlacklistCache()
        db_ids = ["db1", "db2"]
        result = cache.get_blacklisted_channel_ids(fetch_from_db=lambda: db_ids)
        assert result == db_ids

        # Verify it was written to cache file
        with open("/tmp/.test_fallback_cache", "r") as f:
            assert json.loads(f.read()) == db_ids

        os.unlink("/tmp/.test_fallback_cache")

    def test_get_blacklisted_returns_cached_in_memory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", "/tmp/.test_inmem_cache")
        import tvevents.config as cfg
        cfg._settings = None

        cache = BlacklistCache()
        cache._blacklisted_channel_ids = ["mem1", "mem2"]
        result = cache.get_blacklisted_channel_ids()
        assert result == ["mem1", "mem2"]

    def test_flush_clears_in_memory(self) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        cache = BlacklistCache()
        cache._blacklisted_channel_ids = ["a", "b"]
        cache.flush()
        assert cache._blacklisted_channel_ids is None

    def test_no_db_no_file_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tvevents.infrastructure.cache import BlacklistCache

        monkeypatch.setenv("BLACKLIST_CACHE_FILEPATH", "/tmp/.nonexistent_empty_test")
        import tvevents.config as cfg
        cfg._settings = None

        cache = BlacklistCache()
        result = cache.get_blacklisted_channel_ids()
        assert result == []
