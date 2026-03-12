# pylint: disable=E0401,W0621,R0801
from unittest.mock import patch, MagicMock
import pytest
from flask import Flask
from app.routes import init_routes


@pytest.fixture
def app():
    app = Flask(__name__)
    init_routes(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_status_route(client):
    """
    Test the /status route to check if it returns 'OK'.
    """
    response = client.get('/status')
    assert response.data.decode() == 'OK'
    assert response.status_code == 200


@patch('app.routes.SND_RQ_FH_COUNTER', new_callable=MagicMock)
@patch('app.routes.LOGGER')
@patch('app.routes.utils.validate_request')
@patch('app.routes.utils.push_changes_to_firehose')
def test_send_request_firehose_valid_payload(
    mock_push_changes_to_firehose,
    mock_validate_request,
    mock_logger,
    mock_counter,
    client,
):
    """
    Test the / route with a valid JSON payload.
    Ensures that the payload is processed and sent to the firehose.
    """
    payload = {'key': 'value'}
    response = client.post('/', json=payload)
    assert response.data.decode() == 'OK'
    assert response.status_code == 200
    mock_logger.info.assert_called_with('JSON Payload: %s', payload)
    mock_validate_request.assert_called_once()
    mock_push_changes_to_firehose.assert_called_once_with(payload)
    mock_counter.add.assert_called_once_with(1)


@patch('app.routes.LOGGER')
@patch('app.routes.SND_RQ_FH_COUNTER', new_callable=MagicMock)
def test_send_request_firehose_invalid_payload(mock_counter, mock_logger, client):
    """
    Test the / route with an invalid JSON payload.
    Ensures that the exception is handled and logged.
    """
    payload = {'key': 'invalid'}
    response = client.post(
        '/?tvid=12345', json=payload, content_type='application/json'
    )
    assert response.status_code == 400
    mock_logger.error.assert_called_once()
    mock_counter.add.assert_called_once_with(1)


def test_handle_exceptions(client):
    """
    Test the exception handler to check if it returns the correct JSON response.
    """
    response = client.get('/nonexistent_route')
    assert response.status_code == 404


@patch('app.routes.LOGGER')
def test_before_request_logging_failure(mock_logger, client):
    """
    Test that an exception in the before_request logger triggers TvEventsCatchallException.
    """
    # Make LOGGER.info raise an exception
    mock_logger.info.side_effect = Exception("Logging failed")
    response = client.get('/status')

    assert response.status_code == 400
    mock_logger.error.assert_called_once()

    assert (
        b"Exception in before_request" in response.data
        or b"Logging failed" in response.data
    )
