# pylint: disable=E0401,W0621,W0212,R0801
from unittest.mock import patch, MagicMock
import pytest
from app.dbhelper import TvEventsRds


@pytest.fixture
def instance():
    return TvEventsRds()


@patch('app.dbhelper.LOGGER')
def test_blacklisted_channel_ids_fetch_from_rds(mock_logger, instance):
    """
    Test blacklisted_channel_ids when cache is missing and fetching from RDS.
    Ensures that the channel IDs are fetched from RDS and cached properly.
    """
    instance._blacklisted_channel_ids = None
    instance.read_data_from_channel_ids_cache = MagicMock(return_value=None)
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map = MagicMock(
        return_value=[1, 2, 3]
    )
    instance.store_data_in_channel_ids_cache = MagicMock()

    result = instance.blacklisted_channel_ids()

    assert result == [1, 2, 3]
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map.assert_called_once()
    instance.store_data_in_channel_ids_cache.assert_called_once_with([1, 2, 3])
    mock_logger.debug.assert_called_once_with(
        'Fetched blacklisted channel ids from RDS: [1, 2, 3]'
    )


def test_blacklisted_channel_ids_use_existing(instance):
    """
    Test blacklisted_channel_ids when using existing cached data.
    Ensures that the existing cached data is used when cache TTL is not expired.
    """
    instance._blacklisted_channel_ids = [7, 8, 9]

    result = instance.blacklisted_channel_ids()

    assert result == [7, 8, 9]


def test_initialize_blacklisted_channel_ids_cache_success():
    """
    Test initialize_blacklisted_channel_ids_cache when RDS returns channel IDs.
    Ensures that the cache is written and no exception is raised.
    """
    instance = TvEventsRds.__new__(TvEventsRds)  # Avoid calling __init__
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map = MagicMock(
        return_value=[10, 20, 30]
    )
    instance.store_data_in_channel_ids_cache = MagicMock()

    # Should not raise
    instance.initialize_blacklisted_channel_ids_cache()

    instance.store_data_in_channel_ids_cache.assert_called_once_with([10, 20, 30])


def test_initialize_blacklisted_channel_ids_cache_failure():
    """
    Test initialize_blacklisted_channel_ids_cache when RDS returns no channel IDs.
    Ensures that RuntimeError is raised.
    """
    instance = TvEventsRds.__new__(TvEventsRds)  # Avoid calling __init__
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map = MagicMock(
        return_value=[]
    )
    instance.store_data_in_channel_ids_cache = MagicMock()

    with pytest.raises(
        RuntimeError,
        match="Failed to fetch blacklisted channel IDs from RDS at startup.",
    ):
        instance.initialize_blacklisted_channel_ids_cache()


def test_blacklisted_channel_ids_cache_hit(instance):
    """
    Test that blacklisted_channel_ids returns cached data if already set,
    and does not call cache or RDS fetch methods.
    """
    instance._blacklisted_channel_ids = [100, 200]
    instance.read_data_from_channel_ids_cache = MagicMock()
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map = MagicMock()
    result = instance.blacklisted_channel_ids()
    assert result == [100, 200]
    instance.read_data_from_channel_ids_cache.assert_not_called()
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map.assert_not_called()


def test_blacklisted_channel_ids_cache_miss_rds_empty(instance):
    """
    Test that blacklisted_channel_ids returns empty list if cache is missing
    and RDS returns nothing.
    """
    instance._blacklisted_channel_ids = None
    instance.read_data_from_channel_ids_cache = MagicMock(return_value=None)
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map = MagicMock(
        return_value=[]
    )
    instance.store_data_in_channel_ids_cache = MagicMock()
    result = instance.blacklisted_channel_ids()
    assert result == []
    instance.store_data_in_channel_ids_cache.assert_not_called()


def test_blacklisted_channel_ids_cache_miss_rds_success(instance):
    """
    Test that blacklisted_channel_ids fetches from RDS and updates cache if cache is missing.
    """
    instance._blacklisted_channel_ids = None
    instance.read_data_from_channel_ids_cache = MagicMock(return_value=None)
    instance.fetchall_channel_ids_from_blacklisted_station_channel_map = MagicMock(
        return_value=[300, 400]
    )
    instance.store_data_in_channel_ids_cache = MagicMock()
    result = instance.blacklisted_channel_ids()
    assert result == [300, 400]
    instance.store_data_in_channel_ids_cache.assert_called_once_with([300, 400])


def test_store_data_in_channel_ids_cache_writes_file(tmp_path):
    """
    Test that store_data_in_channel_ids_cache writes the correct data to the cache file.
    """
    instance = TvEventsRds()
    cache_file = tmp_path / "cache.json"
    instance.BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH = str(cache_file)
    instance.store_data_in_channel_ids_cache([1, 2, 3])
    with open(cache_file, "r", encoding="utf-8") as f:
        data = f.read()
    assert data == "[1, 2, 3]"


def test_read_data_from_channel_ids_cache_reads_file(tmp_path):
    """
    Test that read_data_from_channel_ids_cache reads
    and returns the correct data from the cache file.
    """
    instance = TvEventsRds()
    cache_file = tmp_path / "cache.json"
    cache_file.write_text("[10, 20, 30]", encoding="utf-8")
    instance.BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH = str(cache_file)
    result = instance.read_data_from_channel_ids_cache()
    assert result == [10, 20, 30]


def test_execute_handles_connection_error(instance):
    """
    Test that _execute returns empty list if connection fails.
    """
    instance._connect = MagicMock(return_value=None)
    result = instance._execute("SELECT 1;")
    assert result == []


def test_execute_handles_query_error(instance):
    """
    Test that _execute returns empty list if query execution fails.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute.side_effect = Exception("Query failed")
    instance._connect = MagicMock(return_value=mock_conn)
    result = instance._execute("SELECT 1;")
    assert result == []
    mock_cursor.close.assert_called_once()
    mock_conn.close.assert_called_once()


def test_fetchall_channel_ids_from_blacklisted_station_channel_map_returns_ids(
    instance,
):
    """
    Test that fetchall_channel_ids_from_blacklisted_station_channel_map returns correct channel IDs.
    """
    instance._execute = MagicMock(
        return_value=[{"channel_id": 123}, {"channel_id": 456}]
    )
    result = instance.fetchall_channel_ids_from_blacklisted_station_channel_map()
    assert result == [123, 456]


def test_store_data_in_channel_ids_cache_ioerror(instance):
    """
    Test that store_data_in_channel_ids_cache logs error if file write fails.
    """
    with patch("builtins.open", side_effect=IOError):
        instance.store_data_in_channel_ids_cache([1, 2, 3])
        # Should log an error, no exception raised


def test_read_data_from_channel_ids_cache_ioerror(instance):
    """
    Test that read_data_from_channel_ids_cache logs error and returns None if file read fails.
    """
    with patch("builtins.open", side_effect=IOError):
        result = instance.read_data_from_channel_ids_cache()
        assert result is None
