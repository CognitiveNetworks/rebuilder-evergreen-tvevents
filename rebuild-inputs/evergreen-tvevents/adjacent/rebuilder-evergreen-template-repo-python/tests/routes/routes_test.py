# pylint: disable=redefined-outer-name
# Disabling because pytest uses this functionality as a best practice.
"""
Unit tests for the FastAPI application routes.

This module uses pytest and unittest.mock to test the routes defined in the FastAPI app.
Fixtures are provided for setting up the FastAPI application and test client.
"""

from unittest.mock import patch, Mock
import pytest
from fastapi.testclient import TestClient
from app import create_app


@pytest.fixture
def app():
    """
    Pytest fixture to create and configure a new FastAPI app instance for each test.

    Returns:
        FastAPI: The configured FastAPI application instance.
    """
    return create_app()


@pytest.fixture
def client(app):
    """
    Pytest fixture to provide a test client for the FastAPI app.

    Args:
        app (FastAPI): The FastAPI application instance.

    Returns:
        TestClient: The FastAPI test client.
    """
    return TestClient(app)


def test_home_route(client):
    """
    Test the / route to check if it returns 'OK' and status code 200.

    Args:
        client (TestClient): The FastAPI test client.

    Asserts:
        The response text is 'OK' and response status code is 200.
    """
    response = client.get('/')
    assert response.text == 'OK'
    assert response.status_code == 200


def test_status_route(client):
    """
    Test the /status route to check if it returns 'OK' and status code 200.

    Args:
        client (TestClient): The FastAPI test client.

    Asserts:
        The response text is 'OK' and response status code is 200.
    """
    response = client.get('/status')
    assert response.text == 'OK'
    assert response.status_code == 200


@patch('app.routes.LOGGER')
def test_request_logging_failure(mock_logger, client):
    """
    Test that an exception in the logging middleware triggers error logging.
    """
    mock_logger.info.side_effect = Exception("Logging failed")
    with pytest.raises(Exception, match="Logging failed"):
        client.post('/s3/upload', json={"key": "test", "data": "test"})
    mock_logger.error.assert_called_once()


@patch('app.routes.http_requests.post')
def test_s3_download_success(mock_post, client):
    """
    Test s3_download returns file contents and 200 when status_code is 200.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "file-content"
    mock_post.return_value = mock_response

    response = client.get('/s3/download/foo.txt')

    assert response.status_code == 200
    assert "file-content" in response.text
    mock_post.assert_called_once()


@patch('app.routes.http_requests.post')
def test_s3_download_failure(mock_post, client):
    """
    Test s3_download returns error JSON and proper status code when status_code is not 200.
    """
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = ""
    mock_post.return_value = mock_response

    response = client.get('/s3/download/foo.txt')

    assert response.status_code == 404
    assert "download failed" in response.text
    mock_post.assert_called_once()
