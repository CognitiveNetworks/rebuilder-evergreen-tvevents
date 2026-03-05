"""Kafka producer service tests — lifecycle, delivery, dead-letter fallback.

Validates KafkaProducerService connect/close/send/flush/health_check
using mocked ``confluent_kafka.Producer`` so no real broker is required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from confluent_kafka import KafkaException

from tests.conftest import TEST_SALT, TEST_ZOO
from tvevents.config import Settings
from tvevents.services.kafka_producer import KafkaProducerService


def _make_settings() -> Settings:
    return Settings(
        t1_salt=TEST_SALT,
        zoo=TEST_ZOO,
        kafka_bootstrap_servers="localhost:9092",
        kafka_security_protocol="PLAINTEXT",
    )


def _make_settings_with_sasl() -> Settings:
    return Settings(
        t1_salt=TEST_SALT,
        zoo=TEST_ZOO,
        kafka_bootstrap_servers="broker.vizio.test:9093",
        kafka_security_protocol="SASL_SSL",
        kafka_sasl_mechanism="PLAIN",
        kafka_sasl_username="vizio-tv-ingest",
        kafka_sasl_password="s3cret",
    )


class TestKafkaProducerLifecycle:
    """Connect / close lifecycle with mocked confluent_kafka.Producer."""

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_connect_creates_producer_with_base_config(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """connect() instantiates Producer with bootstrap.servers and
        standard tuning knobs."""
        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        mock_producer_cls.assert_called_once()
        conf = mock_producer_cls.call_args[0][0]
        assert conf["bootstrap.servers"] == "localhost:9092"
        assert conf["security.protocol"] == "PLAINTEXT"
        assert conf["linger.ms"] == 5
        assert "sasl.mechanism" not in conf

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_connect_includes_sasl_when_configured(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """When SASL settings are present, connect() passes them to the
        Producer config for Vizio's MSK cluster auth."""
        svc = KafkaProducerService(_make_settings_with_sasl())
        await svc.connect()

        conf = mock_producer_cls.call_args[0][0]
        assert conf["sasl.mechanism"] == "PLAIN"
        assert conf["sasl.username"] == "vizio-tv-ingest"
        assert conf["sasl.password"] == "s3cret"

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_close_flushes_and_clears_producer(self, mock_producer_cls: MagicMock) -> None:
        """close() flushes pending messages and sets _producer to None."""
        mock_instance = MagicMock()
        mock_instance.flush.return_value = 0
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()
        await svc.close()

        mock_instance.flush.assert_called_once_with(timeout=10)
        assert svc._producer is None

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_close_warns_on_remaining_unflushed_messages(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """When flush returns remaining > 0, close() logs a warning but
        still tears down the producer."""
        mock_instance = MagicMock()
        mock_instance.flush.return_value = 42
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()
        await svc.close()

        mock_instance.flush.assert_called_once_with(timeout=10)
        assert svc._producer is None

    @pytest.mark.asyncio
    async def test_close_noop_when_not_connected(self) -> None:
        """close() is safe to call even when never connected."""
        svc = KafkaProducerService(_make_settings())
        await svc.close()  # should not raise


class TestKafkaDeliveryCallback:
    """Unit tests for the per-message delivery callback."""

    def test_delivery_callback_logs_error_on_failure(self) -> None:
        """When err is set, _delivery_callback logs an error."""
        svc = KafkaProducerService(_make_settings())
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "tvevents-raw"
        mock_err = MagicMock()

        # Should not raise — it only logs
        svc._delivery_callback(mock_err, mock_msg)

    def test_delivery_callback_logs_debug_on_success(self) -> None:
        """When err is None, _delivery_callback logs partition/offset."""
        svc = KafkaProducerService(_make_settings())
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "tvevents-raw"
        mock_msg.partition.return_value = 3
        mock_msg.offset.return_value = 12345

        svc._delivery_callback(None, mock_msg)

    def test_delivery_callback_handles_none_msg_on_error(self) -> None:
        """When msg is None (edge case), callback still logs safely."""
        svc = KafkaProducerService(_make_settings())
        mock_err = MagicMock()
        svc._delivery_callback(mock_err, None)


class TestKafkaSend:
    """Produce path — normal, BufferError dead-letter, and not-connected."""

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_send_produces_json_payload_to_topic(self, mock_producer_cls: MagicMock) -> None:
        """send() serialises data as compact JSON and produces to the
        given topic (e.g. tvevents-raw for Vizio TV event ingestion)."""
        mock_instance = MagicMock()
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        payload = {"tvid": "ITV00C000000000000001", "event_type": 1}
        await svc.send("tvevents-raw", payload, key="ITV00C000000000000001")

        mock_instance.produce.assert_called_once()
        call_kwargs = mock_instance.produce.call_args[1]
        assert call_kwargs["topic"] == "tvevents-raw"
        assert call_kwargs["value"] == json.dumps(payload, separators=(",", ":")).encode()
        assert call_kwargs["key"] == b"ITV00C000000000000001"
        mock_instance.poll.assert_called_once_with(0)

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_send_without_key(self, mock_producer_cls: MagicMock) -> None:
        """send() passes key_bytes=None when no key is provided."""
        mock_instance = MagicMock()
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        await svc.send("tvevents-raw", {"tvid": "ITV00CA1B2C3D4E5F60007"})

        call_kwargs = mock_instance.produce.call_args[1]
        assert call_kwargs["key"] is None

    @pytest.mark.asyncio
    async def test_send_raises_runtime_error_when_not_connected(self) -> None:
        """send() raises RuntimeError before connect() is called."""
        svc = KafkaProducerService(_make_settings())

        with pytest.raises(RuntimeError, match="not connected"):
            await svc.send("tvevents-raw", {"tvid": "ITV00C000000000000001"})

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_send_falls_back_to_dead_letter_on_buffer_error(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """When the primary produce raises BufferError, send() routes
        the message to <topic>-dlq."""
        mock_instance = MagicMock()
        # First produce call raises BufferError, second (DLQ) succeeds
        mock_instance.produce.side_effect = [BufferError("queue full"), None]
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        await svc.send("tvevents-raw", {"tvid": "ITV00C000000000000001"})

        assert mock_instance.produce.call_count == 2
        dlq_call = mock_instance.produce.call_args_list[1]
        assert dlq_call[1]["topic"] == "tvevents-raw-dlq"

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_send_raises_when_dead_letter_also_fails(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """When both primary and DLQ produces fail, the DLQ exception
        propagates to the caller."""
        mock_instance = MagicMock()
        mock_instance.produce.side_effect = [
            BufferError("queue full"),
            KafkaException(MagicMock(code=lambda: -1, str=lambda: "DLQ fail")),
        ]
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        with pytest.raises(KafkaException):
            await svc.send("tvevents-raw", {"tvid": "ITV00C000000000000001"})


class TestKafkaFlush:
    """flush() delegates to the underlying producer."""

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_flush_calls_producer_flush(self, mock_producer_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()
        await svc.flush()

        mock_instance.flush.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_flush_noop_when_not_connected(self) -> None:
        """flush() is safe to call when producer is None."""
        svc = KafkaProducerService(_make_settings())
        await svc.flush()  # should not raise


class TestKafkaHealthCheck:
    """health_check() validates broker reachability via list_topics."""

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_health_check_returns_true_when_connected(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """When list_topics returns metadata, health_check is True."""
        mock_instance = MagicMock()
        mock_instance.list_topics.return_value = MagicMock()
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        assert await svc.health_check() is True
        mock_instance.list_topics.assert_called_once_with(timeout=5)

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_not_connected(self) -> None:
        """health_check() returns False before connect() is called."""
        svc = KafkaProducerService(_make_settings())
        assert await svc.health_check() is False

    @pytest.mark.asyncio
    @patch("tvevents.services.kafka_producer.Producer")
    async def test_health_check_returns_false_on_kafka_exception(
        self, mock_producer_cls: MagicMock
    ) -> None:
        """When the cluster is unreachable, health_check catches
        KafkaException and returns False."""
        mock_instance = MagicMock()
        mock_instance.list_topics.side_effect = KafkaException(
            MagicMock(code=lambda: -1, str=lambda: "broker down")
        )
        mock_producer_cls.return_value = mock_instance

        svc = KafkaProducerService(_make_settings())
        await svc.connect()

        assert await svc.health_check() is False
