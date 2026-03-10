"""File-based blacklist cache — ported from legacy app/dbhelper.py."""


import json
import logging
from collections.abc import Callable

from tvevents.config import get_settings

logger = logging.getLogger(__name__)


class BlacklistCache:
    """Manages the file-based blacklisted channel IDs cache."""

    def __init__(self) -> None:
        self._blacklisted_channel_ids: list[str] | None = None

    @property
    def cache_filepath(self) -> str:
        """Return the cache file path from settings."""
        return get_settings().blacklist_cache_filepath

    def store(self, channel_ids: list[str]) -> None:
        """Write channel IDs to the cache file."""
        try:
            with open(self.cache_filepath, "w", encoding="utf-8") as f:
                f.write(json.dumps(channel_ids))
            logger.debug("Wrote blacklisted channel ids to cache")
        except IOError:
            logger.error("Couldn't write to blacklisted channel ids cache file.")

    def read(self) -> list[str] | None:
        """Read channel IDs from the cache file."""
        try:
            with open(self.cache_filepath, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
                logger.debug("Read blacklisted channel ids cache")
                return list(data)
        except IOError:
            logger.error("Couldn't open blacklist cache file")
        return None

    def get_blacklisted_channel_ids(
        self, fetch_from_db: Callable[[], list[str]] | None = None
    ) -> list[str]:
        """Get blacklisted channel IDs from cache, falling back to DB.

        If the in-memory list is empty, tries the file cache first.
        If the file cache is missing, calls fetch_from_db to query RDS
        and rebuilds the file cache.
        """
        if self._blacklisted_channel_ids is not None:
            return self._blacklisted_channel_ids

        cached = self.read()
        if cached is not None:
            self._blacklisted_channel_ids = cached
            return self._blacklisted_channel_ids

        if fetch_from_db is not None:
            rds_ids = fetch_from_db()
            if rds_ids:
                logger.debug("Fetched blacklisted channel ids from RDS: %s", rds_ids)
                self.store(rds_ids)
                self._blacklisted_channel_ids = rds_ids
                return self._blacklisted_channel_ids

        self._blacklisted_channel_ids = []
        logger.warning("No blacklisted channel IDs found.")
        return self._blacklisted_channel_ids

    def flush(self) -> None:
        """Clear the in-memory cache, forcing a reload on next access."""
        self._blacklisted_channel_ids = None
        logger.info("Blacklist cache flushed")
