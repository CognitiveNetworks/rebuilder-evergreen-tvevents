"""
Defines and initializes the application routes for the FastAPI web application.

This module sets up logging for the application and provides route definitions
for endpoints such as `/status` for health checks.
"""

import sys
import json
import requests as http_requests
from opentelemetry import trace
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from app import meter, configure_logging

LOGGER = configure_logging()

router = APIRouter()
tracer = trace.get_tracer(__name__)

# Create metrics counters
RQ_COUNTER = meter.create_counter(
    name="request_counter",
    description="Request Counter",
)


async def log_request_middleware(request: Request, call_next):
    """
    Middleware to capture incoming HTTP request and write it to log.
    """
    if request.url.path in ['/status', '/health']:
        return await call_next(request)
    try:
        log_data = {
            'incoming_request': 'access_log',
            'method': request.method,
            'path': request.url.path,
            'remote_client': request.client.host if request.client else None,
            'request_url': str(request.url),
            'headers': dict(request.headers),
        }
        LOGGER.info(json.dumps(log_data, indent=4))
    except Exception as catchall_exception:
        LOGGER.error('Exception in request logging middleware: %s', catchall_exception)
        raise catchall_exception.with_traceback(sys.exc_info()[2])
    return await call_next(request)


@router.get('/')
async def home():
    """
    Home endpoint.

    Returns:
        PlainTextResponse: Simple "OK" response to indicate the service is running.
    """
    RQ_COUNTER.add(1)
    tracer.start_as_current_span('home')
    return PlainTextResponse('OK')


@router.get('/status')
async def status():
    """
    Health check endpoint.

    Returns:
        PlainTextResponse: Simple "OK" response to indicate the service is running.
    """
    RQ_COUNTER.add(1)
    tracer.start_as_current_span('status')
    return PlainTextResponse('OK')


@router.post('/s3/upload')
async def s3_upload(request: Request):
    """
    Upload file to object storage via Dapr binding.
    Expects JSON: {"key": "path/to/file.txt", "data": "content"}
    """
    data = await request.json()
    payload = {
        "operation": "create",
        "metadata": {"key": data["key"]},
        "data": data["data"],
    }
    resp = http_requests.post(
        "http://localhost:3500/v1.0/bindings/object-storage",
        json=payload,
        timeout=30,
    )
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@router.get('/s3/download/{key:path}')
async def s3_download(key: str):
    """
    Download file from object storage via Dapr binding.
    """
    payload = {"operation": "get", "metadata": {"key": key}}
    resp = http_requests.post(
        "http://localhost:3500/v1.0/bindings/object-storage",
        json=payload,
        timeout=30,
    )

    if resp.status_code == 200:
        return PlainTextResponse(resp.text, status_code=200)

    return JSONResponse(
        content={"error": "download failed", "status": resp.status_code},
        status_code=resp.status_code,
    )
