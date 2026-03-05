"""RDS client tests — pool lifecycle, blacklist queries, health checks.

Validates RdsClient connect/close/fetch/health_check using mocked
``asyncpg`` so no real PostgreSQL instance is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_SALT, TEST_ZOO
from tvevents.config import Settings
from tvevents.services.rds_client import RdsClient


def _make_settings() -> Settings:
    return Settings(
        t1_salt=TEST_SALT,
        zoo=TEST_ZOO,
        rds_host="localhost",
        rds_port=5432,
        rds_user="tvevents_app",
        rds_pass="tvevents-rds-2024-xK9mP2",
        rds_db="vizio_tvevents",
    )


class TestRdsClientLifecycle:
    """Connect / close lifecycle with mocked asyncpg pool."""

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_connect_creates_pool_with_correct_dsn(self, mock_asyncpg: MagicMock) -> None:
        """connect() builds the DSN from settings and creates a pool
        sized for Vizio TV event blacklist lookups."""
        mock_pool = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        mock_asyncpg.create_pool.assert_awaited_once()
        call_kwargs = mock_asyncpg.create_pool.call_args[1]
        assert "tvevents_app" in call_kwargs["dsn"]
        assert "tvevents-rds-2024-xK9mP2" in call_kwargs["dsn"]
        assert "localhost" in call_kwargs["dsn"]
        assert "vizio_tvevents" in call_kwargs["dsn"]
        assert call_kwargs["min_size"] == 2
        assert call_kwargs["max_size"] == 10
        assert client._pool is mock_pool

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_close_closes_pool_and_sets_none(self, mock_asyncpg: MagicMock) -> None:
        """close() awaits pool.close() and sets _pool to None."""
        mock_pool = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()
        await client.close()

        mock_pool.close.assert_awaited_once()
        assert client._pool is None

    @pytest.mark.asyncio
    async def test_close_noop_when_pool_is_none(self) -> None:
        """close() is safe to call before connect()."""
        client = RdsClient(_make_settings())
        await client.close()  # should not raise
        assert client._pool is None


class TestFetchBlacklistedChannelIds:
    """Blacklist query — the core lookup for Vizio TV channel filtering."""

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_fetch_returns_channel_id_strings(self, mock_asyncpg: MagicMock) -> None:
        """fetch_blacklisted_channel_ids() converts rows to string IDs
        (e.g. '10501', '99999' for blacklisted Vizio channels)."""
        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(
            return_value=[
                {"channel_id": 10501},
                {"channel_id": 99999},
                {"channel_id": 42},
            ]
        )
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        result = await client.fetch_blacklisted_channel_ids()

        assert result == ["10501", "99999", "42"]
        mock_pool.fetch.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_fetch_returns_empty_list_when_no_blacklisted(
        self, mock_asyncpg: MagicMock
    ) -> None:
        """When the blacklist table is empty, an empty list is returned."""
        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(return_value=[])
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        result = await client.fetch_blacklisted_channel_ids()
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_raises_runtime_error_when_not_connected(self) -> None:
        """fetch_blacklisted_channel_ids() raises RuntimeError before
        connect() is called."""
        client = RdsClient(_make_settings())

        with pytest.raises(RuntimeError, match="not connected"):
            await client.fetch_blacklisted_channel_ids()

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_fetch_propagates_pool_exceptions(self, mock_asyncpg: MagicMock) -> None:
        """Exceptions from pool.fetch() propagate to the caller so the
        lifespan handler can react."""
        mock_pool = AsyncMock()
        mock_pool.fetch = AsyncMock(side_effect=Exception("connection reset by peer"))
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        with pytest.raises(Exception, match="connection reset"):
            await client.fetch_blacklisted_channel_ids()


class TestRdsHealthCheck:
    """health_check() validates database connectivity via SELECT 1."""

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_health_check_returns_true_when_connected(self, mock_asyncpg: MagicMock) -> None:
        """When the pool responds to SELECT 1, health_check returns True."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_cm
        mock_pool.close = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        assert await client.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_not_connected(self) -> None:
        """health_check() returns False when pool is None."""
        client = RdsClient(_make_settings())
        assert await client.health_check() is False

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_health_check_returns_false_on_query_failure(
        self, mock_asyncpg: MagicMock
    ) -> None:
        """When the database is unreachable, health_check catches the
        exception and returns False."""
        mock_pool = AsyncMock()
        mock_pool.acquire.side_effect = Exception("connection refused")
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        assert await client.health_check() is False


class TestRdsPoolMetrics:
    """pool_size / pool_free properties for saturation metrics."""

    def test_pool_size_returns_zero_when_no_pool(self) -> None:
        client = RdsClient(_make_settings())
        assert client.pool_size == 0

    def test_pool_free_returns_zero_when_no_pool(self) -> None:
        client = RdsClient(_make_settings())
        assert client.pool_free == 0

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_pool_size_returns_int_when_pool_exists(self, mock_asyncpg: MagicMock) -> None:
        """pool_size delegates to pool.get_size()."""
        mock_pool = MagicMock()
        mock_pool.get_size.return_value = 5
        mock_pool.close = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        assert client.pool_size == 5

    @pytest.mark.asyncio
    @patch("tvevents.services.rds_client.asyncpg")
    async def test_pool_free_returns_idle_count(self, mock_asyncpg: MagicMock) -> None:
        """pool_free delegates to pool.get_idle_size()."""
        mock_pool = MagicMock()
        mock_pool.get_idle_size.return_value = 3
        mock_pool.close = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        client = RdsClient(_make_settings())
        await client.connect()

        assert client.pool_free == 3
