"""Tests for tvevents.domain.transform module."""

from tests.conftest import make_valid_payload


class TestFlattenRequestJson:
    """Tests for flatten_request_json."""

    def test_flat_dict_lowercases_keys(self) -> None:
        from tvevents.domain.transform import flatten_request_json

        result = flatten_request_json({"Foo": 1, "Bar": "baz"})
        assert result == {"foo": 1, "bar": "baz"}

    def test_nested_dict_prefixes_keys(self) -> None:
        from tvevents.domain.transform import flatten_request_json

        result = flatten_request_json({"channelData": {"channelid": "123", "name": "ABC"}})
        assert result == {"channeldata_channelid": "123", "channeldata_name": "ABC"}

    def test_ignore_keys_string(self) -> None:
        from tvevents.domain.transform import flatten_request_json

        result = flatten_request_json({"Foo": 1, "Bar": 2}, ignore_keys="Foo")
        assert result == {"bar": 2}

    def test_ignore_keys_list(self) -> None:
        from tvevents.domain.transform import flatten_request_json

        result = flatten_request_json({"Foo": 1, "Bar": 2, "Baz": 3}, ignore_keys=["Foo", "Baz"])
        assert result == {"bar": 2}

    def test_empty_dict(self) -> None:
        from tvevents.domain.transform import flatten_request_json

        assert flatten_request_json({}) == {}

    def test_deeply_nested(self) -> None:
        from tvevents.domain.transform import flatten_request_json

        data = {"A": {"B": {"C": 42}}}
        result = flatten_request_json(data)
        assert result == {"b_c": 42}


class TestGetPayloadNamespace:
    """Tests for get_payload_namespace."""

    def test_namespace_key(self) -> None:
        from tvevents.domain.transform import get_payload_namespace

        assert get_payload_namespace({"Namespace": "com.app"}) == "com.app"

    def test_namespace_key_variation(self) -> None:
        from tvevents.domain.transform import get_payload_namespace

        assert get_payload_namespace({"NameSpace": "com.app"}) == "com.app"

    def test_lowercase_namespace(self) -> None:
        from tvevents.domain.transform import get_payload_namespace

        assert get_payload_namespace({"namespace": "com.app"}) == "com.app"

    def test_no_namespace(self) -> None:
        from tvevents.domain.transform import get_payload_namespace

        assert get_payload_namespace({"other": "value"}) is None


class TestGenerateOutputJson:
    """Tests for generate_output_json."""

    def test_acr_tuner_data_output(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.transform import generate_output_json

        payload = make_valid_payload(event_type="ACR_TUNER_DATA")
        result = generate_output_json(payload, "dev", EVENT_TYPE_MAP)

        assert result["tvid"] == "test-tvid-001"
        assert result["client"] == "test-client"
        assert result["tvevent_eventtype"] == "ACR_TUNER_DATA"
        assert result["tvevent_timestamp"] == 1700000000000
        assert result["zoo"] == "dev"
        assert "h" not in result

    def test_output_contains_flattened_event_data(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.transform import generate_output_json

        payload = make_valid_payload(event_type="ACR_TUNER_DATA")
        result = generate_output_json(payload, "dev", EVENT_TYPE_MAP)

        assert "channeldata_channelid" in result or "channelid" in result

    def test_nativeapp_telemetry_output(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.transform import generate_output_json

        event_data = {
            "Timestamp": 1700000000000,
            "Namespace": "com.vizio.app",
            "AppId": "APP001",
            "SomeField": "value",
        }
        payload = make_valid_payload(event_type="NATIVEAPP_TELEMETRY", event_data=event_data)
        result = generate_output_json(payload, "dev", EVENT_TYPE_MAP)

        assert result["tvevent_eventtype"] == "NATIVEAPP_TELEMETRY"
        assert result["namespace"] == "com.vizio.app"
        assert result["appid"] == "APP001"
        assert result["eventdata_timestamp"] == 1700000000000

    def test_platform_telemetry_output(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.transform import generate_output_json

        event_data = {
            "PanelData": {
                "Timestamp": 1700000000000,
                "PanelState": "on",
                "WakeupReason": 1,
            }
        }
        payload = make_valid_payload(event_type="PLATFORM_TELEMETRY", event_data=event_data)
        result = generate_output_json(payload, "dev", EVENT_TYPE_MAP)

        assert result["tvevent_eventtype"] == "PLATFORM_TELEMETRY"
        assert result["paneldata_panelstate"] == "ON"

    def test_unknown_event_type_falls_back(self) -> None:
        from tvevents.domain.event_types import EVENT_TYPE_MAP
        from tvevents.domain.transform import generate_output_json

        event_data = {"CustomField": "value"}
        payload = make_valid_payload(event_type="UNKNOWN_TYPE", event_data=event_data)
        result = generate_output_json(payload, "dev", EVENT_TYPE_MAP)

        assert result["tvevent_eventtype"] == "UNKNOWN_TYPE"
        assert result["customfield"] == "value"
