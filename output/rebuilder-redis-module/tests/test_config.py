"""Tests for RedisSettings configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from rebuilder_redis.config import RedisSettings


class TestDefaults:
    """Verify default values when no environment variables are set."""

    def test_default_host(self) -> None:
        s = RedisSettings()
        assert s.host == "localhost"

    def test_default_port(self) -> None:
        s = RedisSettings()
        assert s.port == 6379

    def test_default_db(self) -> None:
        s = RedisSettings()
        assert s.db == 0

    def test_default_password_is_none(self) -> None:
        s = RedisSettings()
        assert s.password is None

    def test_default_ssl_false(self) -> None:
        s = RedisSettings()
        assert s.ssl is False

    def test_default_socket_timeout(self) -> None:
        s = RedisSettings()
        assert s.socket_timeout == 5.0

    def test_default_max_connections(self) -> None:
        s = RedisSettings()
        assert s.max_connections == 50

    def test_default_decode_responses(self) -> None:
        s = RedisSettings()
        assert s.decode_responses is True

    def test_default_retry_on_timeout(self) -> None:
        s = RedisSettings()
        assert s.retry_on_timeout is True

    def test_default_health_check_interval(self) -> None:
        s = RedisSettings()
        assert s.health_check_interval == 30


class TestEnvironmentOverrides:
    """Verify that REDIS_ prefixed env vars override defaults."""

    def test_host_from_env(self) -> None:
        with patch.dict(os.environ, {"REDIS_HOST": "redis.prod.internal"}):
            s = RedisSettings()
            assert s.host == "redis.prod.internal"

    def test_port_from_env(self) -> None:
        with patch.dict(os.environ, {"REDIS_PORT": "6380"}):
            s = RedisSettings()
            assert s.port == 6380

    def test_password_from_env(self) -> None:
        with patch.dict(os.environ, {"REDIS_PASSWORD": "s3cret-t0ken"}):
            s = RedisSettings()
            assert s.password == "s3cret-t0ken"

    def test_ssl_from_env(self) -> None:
        with patch.dict(os.environ, {"REDIS_SSL": "true"}):
            s = RedisSettings()
            assert s.ssl is True

    def test_max_connections_from_env(self) -> None:
        with patch.dict(os.environ, {"REDIS_MAX_CONNECTIONS": "100"}):
            s = RedisSettings()
            assert s.max_connections == 100

    def test_db_from_env(self) -> None:
        with patch.dict(os.environ, {"REDIS_DB": "3"}):
            s = RedisSettings()
            assert s.db == 3


class TestCustomSettings:
    """Verify that explicit constructor args override defaults."""

    def test_custom_host_and_port(self) -> None:
        s = RedisSettings(host="10.0.1.50", port=6380)
        assert s.host == "10.0.1.50"
        assert s.port == 6380

    def test_custom_ssl_and_password(self) -> None:
        s = RedisSettings(ssl=True, password="prod-pass-v2")
        assert s.ssl is True
        assert s.password == "prod-pass-v2"

    def test_custom_timeouts(self) -> None:
        s = RedisSettings(socket_timeout=2.5, socket_connect_timeout=1.0)
        assert s.socket_timeout == 2.5
        assert s.socket_connect_timeout == 1.0

    def test_custom_pool_size(self) -> None:
        s = RedisSettings(max_connections=200)
        assert s.max_connections == 200
