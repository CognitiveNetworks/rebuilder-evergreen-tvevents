"""Output JSON generation — flatten, classify, obfuscate, deliver."""

import json
import os

from opentelemetry import trace

from app import configure_logging, meter
from app.event_type import flatten_request_json
from app.obfuscation import obfuscate_channel_fields, should_obfuscate_channel
from app.validation import get_event_type_mapping

LOGGER = configure_logging()
tracer = trace.get_tracer(__name__)

ZOO = os.getenv("ZOO", "unknown")

KAFKA_SEND_COUNTER = meter.create_counter(
    name="kafka.send.count",
    description="Kafka message send counter",
)

EVENT_TYPE_COUNTER = meter.create_counter(
    name="event.type.count",
    description="Event type processing counter",
)


def get_payload_namespace(payload: dict) -> str | None:
    """Extract namespace from payload, checking common key casing variants."""
    event_namespace_options = ["Namespace", "NameSpace", "namespace"]
    for option in event_namespace_options:
        if option in payload:
            return payload[option]
    return None


def generate_output_json(request_json: dict) -> dict:
    """
    Generate flattened output JSON for an input payload.

    Flattens TvEvent, adds event type specific data, applies namespace.
    """
    try:
        request_event_type = request_json["TvEvent"]["EventType"]
        output_json: dict = {}
        output_json.update(
            flatten_request_json(
                request_json["TvEvent"], ignore_keys=["h", "timestamp", "EventType"]
            )
        )
        output_json["tvevent_timestamp"] = request_json["TvEvent"]["timestamp"]
        output_json["tvevent_eventtype"] = request_event_type
        output_json["zoo"] = ZOO

        et_map = get_event_type_mapping(output_json["tvevent_eventtype"])

        if et_map:
            et_object = et_map(request_json)
            event_type_output_json = et_object.generate_event_data_output_json()
            output_json.update(event_type_output_json)
            output_json["namespace"] = et_object.namespace
            output_json["appid"] = et_object.appid
        else:
            output_json.update(flatten_request_json(request_json.get("EventData", {})))

        EVENT_TYPE_COUNTER.add(1, {"event_type": request_event_type})
        return output_json
    except KeyError as ke:
        LOGGER.error("generate_output failed: Missing %s, %s", ke, request_json)
        raise
    except Exception as e:
        LOGGER.error("Unhandled exception in generate_output: %s", e)
        raise


def _get_kafka_topics(tvevents_debug: bool = False) -> list[str]:
    """Return the list of active Kafka topics based on env var toggles."""
    topics: list[str] = []

    if tvevents_debug:
        if os.getenv("SEND_EVERGREEN", "false").lower() == "true":
            topic = os.getenv("KAFKA_TOPIC_EVERGREEN_DEBUG", "evergreen-tvevents-debug")
            topics.append(topic)
        if os.getenv("SEND_LEGACY", "false").lower() == "true":
            topic = os.getenv("KAFKA_TOPIC_LEGACY_DEBUG", "legacy-tvevents-debug")
            topics.append(topic)
    else:
        if os.getenv("SEND_EVERGREEN", "false").lower() == "true":
            topic = os.getenv("KAFKA_TOPIC_EVERGREEN", "evergreen-tvevents")
            topics.append(topic)
        if os.getenv("SEND_LEGACY", "false").lower() == "true":
            topic = os.getenv("KAFKA_TOPIC_LEGACY", "legacy-tvevents")
            topics.append(topic)

    return topics


def send_to_kafka(data: dict, topics: list[str]):
    """Send data to Kafka topics via standalone Kafka module."""
    with tracer.start_as_current_span("send_to_kafka"):
        try:
            from kafka_module import send_message

            tvid = data.get("tvid", "")
            payload_bytes = json.dumps(data).encode("utf-8")

            for topic in topics:
                try:
                    send_message(topic, payload_bytes, key=tvid)
                    KAFKA_SEND_COUNTER.add(1, {"topic": topic, "status": "success"})
                except Exception as err:
                    KAFKA_SEND_COUNTER.add(1, {"topic": topic, "status": "failure"})
                    LOGGER.error("Kafka send error for topic %s: %s", topic, err)
                    raise

            LOGGER.debug("payload submitted to Kafka topics: %s", topics)
        except ImportError:
            LOGGER.error("kafka_module not available — cannot send to Kafka")
            raise
        except Exception as ee:
            LOGGER.error("send_to_kafka failed: tvid=%s - %s", data.get("tvid"), ee)
            raise


def push_changes_to_kafka(payload: dict):
    """Process request payload and deliver to Kafka."""
    output_json = generate_output_json(payload)

    tvevents_debug = os.getenv("TVEVENTS_DEBUG", "false").lower() == "true"
    LOGGER.debug("TVEVENTS_DEBUG is: %s", tvevents_debug)

    with tracer.start_as_current_span("push_changes_to_kafka"):
        if should_obfuscate_channel(output_json):
            # send to debug topics before obfuscation
            if tvevents_debug:
                debug_topics = _get_kafka_topics(tvevents_debug=True)
                if debug_topics:
                    send_to_kafka(output_json, debug_topics)

            LOGGER.debug(
                "Obfuscating: tvid=%s, channel_id=%s, iscontentblocked=%s",
                output_json.get("tvid"),
                output_json.get("channelid"),
                output_json.get("iscontentblocked"),
            )
            obfuscate_channel_fields(output_json)

        # send output to active Kafka topics
        topics = _get_kafka_topics(tvevents_debug=False)
        if topics:
            send_to_kafka(output_json, topics)
