"""Tests for app.output module."""

from unittest.mock import patch

import pytest

from app.output import (
    _get_kafka_topics,
    generate_output_json,
    push_changes_to_kafka,
    send_to_kafka,
)


class TestGenerateOutputJson:
    def test_generates_basic_output(self, sample_nativeapp_payload):
        result = generate_output_json(sample_nativeapp_payload)
        assert isinstance(result, dict)
        assert "tvevent_eventtype" in result
        assert "zoo" in result

    def test_includes_tvid(self, sample_nativeapp_payload):
        result = generate_output_json(sample_nativeapp_payload)
        assert "tvid" in result
        assert result["tvid"] == "VZR2023A7F4E9B01"

    def test_includes_timestamp(self, sample_nativeapp_payload):
        result = generate_output_json(sample_nativeapp_payload)
        assert "tvevent_timestamp" in result

    def test_includes_event_type(self, sample_nativeapp_payload):
        result = generate_output_json(sample_nativeapp_payload)
        assert result["tvevent_eventtype"] == "NATIVEAPP_TELEMETRY"


class TestGetKafkaTopics:
    def test_evergreen_enabled(self):
        with patch.dict(
            "os.environ",
            {
                "SEND_EVERGREEN": "true",
                "SEND_LEGACY": "false",
                "KAFKA_TOPIC_EVERGREEN": "eg-topic",
            },
        ):
            topics = _get_kafka_topics(tvevents_debug=False)
            assert "eg-topic" in topics

    def test_legacy_enabled(self):
        with patch.dict(
            "os.environ",
            {
                "SEND_EVERGREEN": "false",
                "SEND_LEGACY": "true",
                "KAFKA_TOPIC_LEGACY": "lg-topic",
            },
        ):
            topics = _get_kafka_topics(tvevents_debug=False)
            assert "lg-topic" in topics

    def test_debug_topics_included(self):
        with patch.dict(
            "os.environ",
            {
                "SEND_EVERGREEN": "true",
                "SEND_LEGACY": "false",
                "KAFKA_TOPIC_EVERGREEN": "eg-topic",
                "KAFKA_TOPIC_EVERGREEN_DEBUG": "eg-debug",
            },
        ):
            topics = _get_kafka_topics(tvevents_debug=True)
            assert "eg-debug" in topics

    def test_no_topics_when_all_disabled(self):
        with patch.dict(
            "os.environ", {"SEND_EVERGREEN": "false", "SEND_LEGACY": "false"}
        ):
            topics = _get_kafka_topics(tvevents_debug=False)
            assert len(topics) == 0


class TestSendToKafka:
    def test_sends_to_each_topic(self, mock_kafka_module):
        data = {"tvid": "abc", "key": "value"}
        send_to_kafka(data, ["topic-1", "topic-2"])
        assert mock_kafka_module.send_message.call_count == 2

    def test_handles_send_failure(self, mock_kafka_module):
        mock_kafka_module.send_message.side_effect = Exception("Kafka down")
        data = {"tvid": "abc", "key": "value"}
        with pytest.raises(Exception, match="Kafka down"):
            send_to_kafka(data, ["topic-1"])


class TestPushChangesToKafka:
    def test_processes_and_sends(self, sample_nativeapp_payload, mock_kafka_module):
        push_changes_to_kafka(sample_nativeapp_payload)
        assert mock_kafka_module.send_message.called
