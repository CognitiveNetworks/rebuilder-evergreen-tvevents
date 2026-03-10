"""Kafka topic delivery — replaces legacy Firehose delivery."""


import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

_kafka_producer: Any = None


def get_kafka_producer() -> Any:
    """Get or create the singleton Kafka producer."""
    global _kafka_producer  # noqa: PLW0603
    if _kafka_producer is None:
        try:
            from confluent_kafka import Producer

            from tvevents.config import get_settings

            settings = get_settings()
            conf: dict[str, Any] = {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": settings.service_name,
            }
            if settings.kafka_security_protocol != "PLAINTEXT":
                conf["security.protocol"] = settings.kafka_security_protocol
                conf["sasl.mechanism"] = settings.kafka_sasl_mechanism
                conf["sasl.username"] = settings.kafka_sasl_username
                conf["sasl.password"] = settings.kafka_sasl_password

            _kafka_producer = Producer(conf)
            logger.info("Kafka producer initialized")
        except Exception as e:
            logger.error("Failed to initialize Kafka producer: %s", e)
            raise
    return _kafka_producer


def _delivery_callback(err: Any, msg: Any) -> None:
    """Kafka delivery report callback."""
    if err is not None:
        logger.error("Kafka delivery failed: %s", err)
    else:
        logger.debug(
            "Kafka message delivered to %s [%s]",
            msg.topic(),
            msg.partition(),
        )


def send_to_topics(
    data: dict[str, Any],
    topics: list[str],
) -> None:
    """Send data to all given Kafka topics in parallel."""
    if not topics:
        logger.warning("No Kafka topics configured — skipping delivery")
        return

    def send(topic: str) -> None:
        try:
            producer = get_kafka_producer()
            producer.produce(
                topic,
                value=json.dumps(data).encode("utf-8"),
                callback=_delivery_callback,
            )
            producer.poll(0)
        except Exception as err:
            logger.error("Kafka produce error for topic %s: %s", topic, err)

    try:
        with ThreadPoolExecutor() as executor:
            executor.map(send, topics)
        logger.debug("Payload submitted to topics: %s", topics)
    except Exception as e:
        logger.error(
            "send_to_topics failed: tvid=%s - %s", data.get("tvid"), e
        )


def flush_producer(timeout: float = 5.0) -> None:
    """Flush the Kafka producer, waiting for all messages to be delivered."""
    if _kafka_producer is not None:
        _kafka_producer.flush(timeout)


def close_producer() -> None:
    """Flush and release the Kafka producer."""
    global _kafka_producer  # noqa: PLW0603
    if _kafka_producer is not None:
        _kafka_producer.flush(10)
        _kafka_producer = None
        logger.info("Kafka producer closed")
