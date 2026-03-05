"""Kafka producer service — replaces legacy Kinesis Data Firehose delivery.

Wraps ``confluent_kafka.Producer`` with async helpers, OTEL tracing, and
dead-letter topic fallback.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from confluent_kafka import KafkaError, KafkaException, Producer
from opentelemetry import trace

if TYPE_CHECKING:
    from tvevents.config import Settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class KafkaProducerService:
    """Async-friendly wrapper around ``confluent_kafka.Producer``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: Producer | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialise the Kafka producer."""
        conf: dict[str, Any] = {
            "bootstrap.servers": self._settings.kafka_bootstrap_servers,
            "security.protocol": self._settings.kafka_security_protocol,
            "client.id": self._settings.service_name,
            "linger.ms": 5,
            "batch.num.messages": 10000,
            "queue.buffering.max.messages": 100000,
            "message.timeout.ms": 30000,
        }

        if self._settings.kafka_sasl_mechanism:
            conf["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
        if self._settings.kafka_sasl_username:
            conf["sasl.username"] = self._settings.kafka_sasl_username
        if self._settings.kafka_sasl_password:
            conf["sasl.password"] = self._settings.kafka_sasl_password

        self._producer = Producer(conf)
        logger.info(
            "Kafka producer connected to %s",
            self._settings.kafka_bootstrap_servers,
        )

    async def close(self) -> None:
        """Flush pending messages and tear down the producer."""
        if self._producer is not None:
            remaining = self._producer.flush(timeout=10)
            if remaining > 0:
                logger.warning("Kafka producer closed with %d un-flushed messages", remaining)
            self._producer = None
            logger.info("Kafka producer closed")

    # ── Produce ──────────────────────────────────────────────────────────

    def _delivery_callback(self, err: KafkaError | None, msg: Any) -> None:
        """Per-message delivery report."""
        if err is not None:
            logger.error(
                "Kafka delivery failed: topic=%s err=%s",
                msg.topic() if msg else "unknown",
                err,
            )
        else:
            logger.debug(
                "Kafka delivered: topic=%s partition=%s offset=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )

    async def send(
        self,
        topic: str,
        data: dict[str, Any],
        key: str | None = None,
    ) -> None:
        """Serialise *data* as JSON and produce to *topic*.

        Falls back to the dead-letter topic (``<topic>-dlq``) if the
        initial produce raises a ``BufferError``.
        """
        if self._producer is None:
            raise RuntimeError("Kafka producer is not connected — call connect() first")

        with tracer.start_as_current_span("kafka.produce") as span:
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)

            payload_bytes = json.dumps(data, separators=(",", ":")).encode()
            key_bytes = key.encode() if key else None

            try:
                self._producer.produce(
                    topic=topic,
                    value=payload_bytes,
                    key=key_bytes,
                    callback=self._delivery_callback,
                )
                self._producer.poll(0)
            except BufferError:
                logger.warning(
                    "Kafka local queue full — routing to dead-letter topic %s-dlq",
                    topic,
                )
                span.add_event("dead_letter_fallback")
                try:
                    self._producer.produce(
                        topic=f"{topic}-dlq",
                        value=payload_bytes,
                        key=key_bytes,
                        callback=self._delivery_callback,
                    )
                    self._producer.poll(0)
                except (BufferError, KafkaException) as dlq_err:
                    logger.error("Dead-letter produce failed: %s", dlq_err)
                    span.record_exception(dlq_err)
                    raise

    async def flush(self) -> None:
        """Flush all buffered messages (blocking up to 10 s)."""
        if self._producer is not None:
            self._producer.flush(timeout=10)

    # ── Health ───────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Return ``True`` if the Kafka cluster is reachable (metadata request)."""
        if self._producer is None:
            return False
        try:
            start = time.monotonic()
            self._producer.list_topics(timeout=5)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.debug("Kafka health check OK (%.1f ms)", elapsed_ms)
            return True
        except KafkaException as exc:
            logger.error("Kafka health check failed: %s", exc)
            return False
