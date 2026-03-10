"""Tests for tvevents API routes — POST /, GET /status, GET /health."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.conftest import make_valid_payload


class TestStatusEndpoint:
    """Tests for GET /status."""

    def test_status_returns_ok(self, client: TestClient) -> None:
        response = client.get("/status")
        assert response.status_code == 200
        assert response.json() == "OK"


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == "OK"


class TestIngestEndpoint:
    """Tests for POST /."""

    @patch("tvevents.api.routes.send_to_topics")
    @patch("tvevents.api.routes.get_blacklist_cache")
    @patch("tvevents.api.routes.get_rds_client")
    def test_valid_payload_returns_ok(
        self, mock_rds, mock_cache, mock_send, client: TestClient
    ) -> None:
        mock_cache_instance = mock_cache.return_value
        mock_cache_instance.get_blacklisted_channel_ids.return_value = []

        payload = make_valid_payload()
        response = client.post(
            "/?tvid=test-tvid-001&event_type=ACR_TUNER_DATA",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "OK"
        mock_send.assert_called()

    @patch("tvevents.api.routes.send_to_topics")
    @patch("tvevents.api.routes.get_blacklist_cache")
    @patch("tvevents.api.routes.get_rds_client")
    def test_missing_required_param_returns_400(
        self, mock_rds, mock_cache, mock_send, client: TestClient
    ) -> None:
        payload = make_valid_payload()
        del payload["TvEvent"]["tvid"]
        response = client.post("/?tvid=test-tvid-001&event_type=ACR_TUNER_DATA", json=payload)
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "TvEventsMissingRequiredParamError"

    @patch("tvevents.api.routes.send_to_topics")
    @patch("tvevents.api.routes.get_blacklist_cache")
    @patch("tvevents.api.routes.get_rds_client")
    def test_invalid_hash_returns_400(
        self, mock_rds, mock_cache, mock_send, client: TestClient
    ) -> None:
        payload = make_valid_payload()
        payload["TvEvent"]["h"] = "wrong-hash-value"
        response = client.post("/?tvid=test-tvid-001&event_type=ACR_TUNER_DATA", json=payload)
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "TvEventsSecurityValidationError"

    @patch("tvevents.api.routes.send_to_topics")
    @patch("tvevents.api.routes.get_blacklist_cache")
    @patch("tvevents.api.routes.get_rds_client")
    def test_content_blocked_triggers_obfuscation(
        self, mock_rds, mock_cache, mock_send, client: TestClient
    ) -> None:
        mock_cache_instance = mock_cache.return_value
        mock_cache_instance.get_blacklisted_channel_ids.return_value = []

        payload = make_valid_payload(
            event_data={
                "channelid": "99999",
                "programid": "PROG1",
                "channelname": "ESPN",
                "iscontentblocked": True,
                "channelData": {
                    "majorId": 1,
                    "minorId": 0,
                },
            },
        )
        response = client.post(
            "/?tvid=test-tvid-001&event_type=ACR_TUNER_DATA",
            json=payload,
        )
        assert response.status_code == 200

        # Verify the sent data had obfuscated fields
        call_args = mock_send.call_args_list[-1]
        sent_data = call_args[0][0]
        assert sent_data["channelid"] == "OBFUSCATED"
        assert sent_data["programid"] == "OBFUSCATED"
        assert sent_data["channelname"] == "OBFUSCATED"

    @patch("tvevents.api.routes.send_to_topics")
    @patch("tvevents.api.routes.get_blacklist_cache")
    @patch("tvevents.api.routes.get_rds_client")
    def test_non_blacklisted_channel_not_obfuscated(
        self, mock_rds, mock_cache, mock_send, client: TestClient
    ) -> None:
        mock_cache_instance = mock_cache.return_value
        mock_cache_instance.get_blacklisted_channel_ids.return_value = ["00000"]

        payload = make_valid_payload()
        response = client.post(
            "/?tvid=test-tvid-001&event_type=ACR_TUNER_DATA",
            json=payload,
        )
        assert response.status_code == 200

        call_args = mock_send.call_args_list[-1]
        sent_data = call_args[0][0]
        assert sent_data.get("channelid") != "OBFUSCATED"
