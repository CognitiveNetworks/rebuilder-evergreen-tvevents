"""Async PostgreSQL (RDS) client — replaces legacy synchronous ``psycopg2`` usage.

Uses ``asyncpg`` connection pooling for efficient blacklist lookups.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import asyncpg
from opentelemetry import trace

if TYPE_CHECKING:
    from tvevents.config import Settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# The query matches the legacy ``fetchall_channel_ids_from_blacklisted_station_channel_map``
_BLACKLIST_QUERY = (
    "SELECT DISTINCT channel_id FROM public.tvevents_blacklisted_station_channel_map"
)


class RdsClient:
    """Async PostgreSQL client backed by an ``asyncpg`` connection pool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Create the connection pool."""
        dsn = (
            f"postgresql://{self._settings.rds_user}:{self._settings.rds_pass}"
            f"@{self._settings.rds_host}:{self._settings.rds_port}"
            f"/{self._settings.rds_db}"
        )

        self._pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=2,
            max_size=10,
            command_timeout=10,
            statement_cache_size=0,
        )
        logger.info(
            "RDS pool created: host=%s db=%s user=%s port=%d",
            self._settings.rds_host,
            self._settings.rds_db,
            self._settings.rds_user,
            self._settings.rds_port,
        )

    async def close(self) -> None:
        """Gracefully close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("RDS pool closed")

    # ── Queries ──────────────────────────────────────────────────────────

    async def fetch_blacklisted_channel_ids(self) -> list[str]:
        """Return all distinct blacklisted channel IDs from RDS.

        Faithfully replicates the legacy blacklist channel map query.
        """
        if self._pool is None:
            raise RuntimeError("RDS client is not connected — call connect() first")

        with tracer.start_as_current_span("rds.fetch_blacklisted_channel_ids") as span:
            span.set_attribute("db.system", "postgresql")
            span.set_attribute("db.statement", _BLACKLIST_QUERY)
            start = time.monotonic()

            try:
                rows: list[asyncpg.Record] = await self._pool.fetch(_BLACKLIST_QUERY)
                elapsed_ms = (time.monotonic() - start) * 1000
                channel_ids: list[str] = [str(row["channel_id"]) for row in rows]
                span.set_attribute("db.rows_affected", len(channel_ids))
                span.set_attribute("db.query_duration_ms", elapsed_ms)
                logger.info(
                    "Fetched %d blacklisted channel IDs from RDS (%.1f ms)",
                    len(channel_ids),
                    elapsed_ms,
                )
                return channel_ids
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                logger.error("RDS blacklist query failed after %.1f ms: %s", elapsed_ms, exc)
                raise

    # ── Health ───────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return ``True`` if the database responds to ``SELECT 1``."""
        if self._pool is None:
            return False
        try:
            start = time.monotonic()
            async with self._pool.acquire(timeout=5) as conn:
                await conn.fetchval("SELECT 1")
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.debug("RDS health check OK (%.1f ms)", elapsed_ms)
            return True
        except Exception as exc:
            logger.error("RDS health check failed: %s", exc)
            return False

    @property
    def pool_size(self) -> int:
        """Current pool size (for saturation metrics)."""
        if self._pool is None:
            return 0
        return int(self._pool.get_size())

    @property
    def pool_free(self) -> int:
        """Number of free connections in the pool."""
        if self._pool is None:
            return 0
        return int(self._pool.get_idle_size())
