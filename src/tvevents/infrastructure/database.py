"""RDS client wrapper — uses psycopg2 for blacklist channel lookups."""


import logging
import time
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from tvevents.config import get_settings

logger = logging.getLogger(__name__)


class RdsClient:
    """PostgreSQL client for tvevents blacklisted channel lookups."""

    def __init__(self) -> None:
        self._connection: Any | None = None

    def _connect(self) -> Any:
        """Create a new database connection."""
        settings = get_settings()
        try:
            connection = psycopg2.connect(
                host=settings.rds_host,
                database=settings.rds_db,
                user=settings.rds_user,
                password=settings.rds_pass,
                port=settings.rds_port,
                connect_timeout=10,
            )
            logger.info(
                "Connected to RDS: host=%s, database=%s",
                settings.rds_host,
                settings.rds_db,
            )
            return connection
        except Exception as e:
            logger.error("RDS connection failed: %s", e)
            raise

    def _execute(self, query: str) -> list[dict[str, Any]]:
        """Execute a query and return results."""
        connection = None
        cur = None
        start_time = time.monotonic()

        try:
            connection = self._connect()
            cur = connection.cursor(cursor_factory=RealDictCursor)
            cur.execute(query)
            output = cur.fetchall()

            duration = time.monotonic() - start_time
            logger.info(
                "RDS query completed: %d rows, %.3fs",
                len(output),
                duration,
            )
            return list(output)
        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error("RDS query failed after %.3fs: %s", duration, e)
            return []
        finally:
            if cur:
                cur.close()
            if connection:
                connection.close()

    def fetch_blacklisted_channel_ids(self) -> list[str]:
        """Fetch all blacklisted channel IDs from RDS."""
        query = """
            SELECT DISTINCT channel_id
            FROM public.tvevents_blacklisted_station_channel_map;
        """
        rows = self._execute(query)
        return [row["channel_id"] for row in rows if row.get("channel_id")]

    def health_check(self) -> bool:
        """Check RDS connectivity."""
        try:
            connection = self._connect()
            cur = connection.cursor()
            cur.execute("SELECT 1")
            cur.close()
            connection.close()
            return True
        except Exception as e:
            logger.error("RDS health check failed: %s", e)
            return False
