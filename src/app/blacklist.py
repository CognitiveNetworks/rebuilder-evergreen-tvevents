"""3-tier blacklist cache: memory -> file -> RDS (via standalone module)."""

import json
import os
import time

from opentelemetry import trace

from app import configure_logging, meter

LOGGER = configure_logging()
tracer = trace.get_tracer(__name__)

CACHE_READ_COUNTER = meter.create_counter(
    name="cache.read.count",
    description="Cache read counter",
)
CACHE_WRITE_COUNTER = meter.create_counter(
    name="cache.write.count",
    description="Cache write counter",
)


class BlacklistCache:
    """
    3-tier blacklist channel IDs cache.

    Priority: memory -> file -> RDS.
    File path controlled by BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH env var.
    """

    def __init__(self):
        """Initialize cache with empty state and file path from env."""
        self.cache_filepath = os.environ.get(
            "BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH",
            "/tmp/.blacklisted_channel_ids_cache",  # noqa: S108
        )
        self._channel_ids: list[str] | None = None
        self._last_refresh: float = 0.0

    def initialize(self):
        """Fetch channel IDs from RDS and cache to file at startup."""
        try:
            channel_ids = self._fetch_from_rds()
            if channel_ids:
                self._write_cache(channel_ids)
                self._channel_ids = channel_ids
                self._last_refresh = time.time()
                LOGGER.info(
                    "Blacklist cache initialized with %d entries", len(channel_ids)
                )
                return
        except Exception as e:
            LOGGER.warning(
                "Failed to fetch blacklisted channel IDs from RDS at startup: %s", e
            )

        # Fallback: try reading from file cache
        cached = self._read_cache()
        if cached is not None:
            self._channel_ids = cached
            self._last_refresh = time.time()
            LOGGER.warning(
                "Using stale file cache with %d entries (RDS unavailable at startup)",
                len(cached),
            )
        else:
            self._channel_ids = []
            LOGGER.warning("No blacklisted channel IDs available at startup")

    def refresh(self):
        """Refresh cache from RDS."""
        with tracer.start_as_current_span("blacklist_cache.refresh"):
            channel_ids = self._fetch_from_rds()
            if channel_ids:
                self._write_cache(channel_ids)
                self._channel_ids = channel_ids
                self._last_refresh = time.time()
                LOGGER.info(
                    "Blacklist cache refreshed with %d entries", len(channel_ids)
                )
                return True
            LOGGER.warning("Blacklist cache refresh failed — no data from RDS")
            return False

    def get_channel_ids(self) -> list[str]:
        """Return the current list of blacklisted channel IDs."""
        with tracer.start_as_current_span("blacklist_cache.get_channel_ids"):
            if self._channel_ids is not None:
                CACHE_READ_COUNTER.add(1, {"tier": "memory", "result": "hit"})
                return self._channel_ids

            # Try file cache
            cached = self._read_cache()
            if cached is not None:
                self._channel_ids = cached
                CACHE_READ_COUNTER.add(1, {"tier": "file", "result": "hit"})
                return self._channel_ids

            # Fall back to RDS
            rds_ids = self._fetch_from_rds()
            if rds_ids:
                self._write_cache(rds_ids)
                self._channel_ids = rds_ids
                CACHE_READ_COUNTER.add(1, {"tier": "db", "result": "hit"})
                return self._channel_ids

            CACHE_READ_COUNTER.add(1, {"tier": "db", "result": "miss"})
            self._channel_ids = []
            LOGGER.warning("No blacklisted channel IDs found.")
            return self._channel_ids

    def is_blacklisted(self, channel_id: str | None) -> bool:
        """Check if a channel_id is in the blacklist."""
        if channel_id is None:
            return False
        LOGGER.debug("Checking if channel is blacklisted: %s", channel_id)
        return str(channel_id) in self.get_channel_ids()

    @property
    def entry_count(self) -> int:
        """Return number of cached blacklisted channel IDs."""
        return len(self._channel_ids) if self._channel_ids else 0

    @property
    def last_refresh_time(self) -> float:
        """Return epoch timestamp of last cache refresh."""
        return self._last_refresh

    @property
    def age_seconds(self) -> float:
        """Return seconds since last cache refresh."""
        if self._last_refresh == 0.0:
            return 0.0
        return time.time() - self._last_refresh

    def _read_cache(self) -> list[str] | None:
        """Read blacklisted channel IDs from file cache."""
        with tracer.start_as_current_span("blacklist_cache.read_file"):
            try:
                with open(self.cache_filepath, encoding="utf-8") as f:
                    LOGGER.debug("Read blacklisted channel ids cache")
                    CACHE_READ_COUNTER.add(1, {"tier": "file", "result": "hit"})
                    return json.loads(f.read())
            except (OSError, json.JSONDecodeError):
                LOGGER.error("Couldn't open blacklist cache file")
                CACHE_READ_COUNTER.add(1, {"tier": "file", "result": "miss"})
                return None

    def _write_cache(self, channel_ids: list[str]):
        """Write channel IDs to file cache."""
        with tracer.start_as_current_span("blacklist_cache.write_file"):
            try:
                with open(self.cache_filepath, "w", encoding="utf-8") as f:
                    f.write(json.dumps(channel_ids))
                    CACHE_WRITE_COUNTER.add(1, {"target": "file"})
                    LOGGER.debug("Wrote blacklisted channel ids to cache")
            except OSError:
                LOGGER.error("Couldn't write to blacklisted channel ids cache file.")

    def _fetch_from_rds(self) -> list[str]:
        """Fetch blacklisted channel IDs from RDS via standalone module."""
        with tracer.start_as_current_span("blacklist_cache.fetch_rds"):
            try:
                from rds_module import execute_query

                query = (
                    "SELECT DISTINCT channel_id"
                    " FROM public.tvevents_blacklisted_station_channel_map;"
                )
                rows = execute_query(query)
                return [row.get("channel_id") for row in rows if row.get("channel_id")]
            except Exception as e:
                LOGGER.error("RDS fetch failed: %s", e)
                return []


# Module-level singleton
blacklist_cache = BlacklistCache()
