# pylint: disable=E0401,W0621,R0801
import pytest
from app.utils import verify_required_params, TvEventsMissingRequiredParamError


def test_verify_required_params_all_params_present():
    """
    Test verify_required_params with all required parameters present.

    The payload contains all required parameters: tvid, client, h, EventType, and timestamp.
    The function should return True.
    """
    payload_params = {
        "tvid": "123",
        "client": "client1",
        "h": "some_hash",
        "EventType": "event",
        "timestamp": "2025-03-05T23:24:47Z",
    }
    assert verify_required_params(payload_params) is True


def test_verify_required_params_missing_param():
    """
    Test verify_required_params with a missing parameter.

    The payload is missing the required parameter EventType.
    The function should raise TvEventsMissingRequiredParamError
     with the message "Missing Required Param: EventType".
    """
    payload_params = {
        "tvid": "123",
        "client": "client1",
        "h": "some_hash",
        "timestamp": "2025-03-05T23:24:47Z",
    }
    with pytest.raises(
        TvEventsMissingRequiredParamError, match="Missing Required Param: EventType"
    ):
        verify_required_params(payload_params)


def test_verify_required_params_default_required_params():
    """
    Test verify_required_params with default required parameters.

    The payload contains all default required parameters: tvid, client, h, EventType, and timestamp.
    The function should return True.
    """
    payload = {
        "TvEvent": {
            "tvid": "123",
            "client": "client1",
            "h": "some_hash",
            "EventType": "event",
            "timestamp": "2025-03-05T23:24:47Z",
        }
    }
    assert verify_required_params(payload) is True


def test_verify_required_params_with_tvid():
    """
    Test verify_required_params with a missing tvid parameter.

    The payload is missing the required parameter tvid,
    but tvid is provided as an argument.

    The function should raise TvEventsMissingRequiredParamError
    with the message "Missing Required Param: tvid tvid=12345".
    """
    payload = {
        "TvEvent": {
            "client": "client1",
            "h": "some_hash",
            "EventType": "event",
            "timestamp": "2025-03-05T23:24:47Z",
        }
    }
    with pytest.raises(
        TvEventsMissingRequiredParamError,
        match="Missing Required Param: tvid",
    ):
        verify_required_params(payload)


def test_verify_required_params_with_event_type():
    """
    Test verify_required_params with a missing EventType parameter.

    The payload is missing the required parameter EventType,
    but EventType is provided as an argument.

    The function should raise TvEventsMissingRequiredParamError
    with the message "Missing Required Param: EventType EventType=eventX".
    """
    payload = {
        "TvEvent": {
            "tvid": "123",
            "client": "client1",
            "h": "some_hash",
            "timestamp": "2025-03-05T23:24:47Z",
        }
    }
    with pytest.raises(
        TvEventsMissingRequiredParamError,
        match="Missing Required Param: EventType",
    ):
        verify_required_params(payload)


def test_verify_required_params_with_tvid_and_event_type():
    """
    Test verify_required_params with missing tvid and EventType parameters.

    The payload is missing the required parameters tvid
    and EventType, but both are provided as arguments.

    The function should raise TvEventsMissingRequiredParamError
    with the message "Missing Required Param: tvid tvid=12345 EventType=eventX".
    """
    payload = {
        "TvEvent": {
            "h": "554ab50be11666cf2c4c4c196448faa8",
            "client": "acr",
            "timestamp": 1599860922441,
        }
    }
    with pytest.raises(
        TvEventsMissingRequiredParamError,
        match="Missing Required Param: tvid",
    ):
        verify_required_params(payload)
