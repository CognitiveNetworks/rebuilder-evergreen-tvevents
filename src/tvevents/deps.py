"""Singleton dependency holders — avoids circular imports between main, routes, and ops."""



from tvevents.infrastructure.cache import BlacklistCache
from tvevents.infrastructure.database import RdsClient

_rds_client: RdsClient | None = None
_blacklist_cache: BlacklistCache | None = None


def get_rds_client() -> RdsClient:
    """Get the singleton RDS client."""
    global _rds_client  # noqa: PLW0603
    if _rds_client is None:
        _rds_client = RdsClient()
    return _rds_client


def get_blacklist_cache() -> BlacklistCache:
    """Get the singleton blacklist cache."""
    global _blacklist_cache  # noqa: PLW0603
    if _blacklist_cache is None:
        _blacklist_cache = BlacklistCache()
    return _blacklist_cache


def reset() -> None:
    """Reset singletons — used in tests."""
    global _rds_client, _blacklist_cache  # noqa: PLW0603
    _rds_client = None
    _blacklist_cache = None
