"""Core API routes — POST /, GET /status, GET /health."""


import logging
import sys
from typing import Any

from fastapi import APIRouter, Request, Response

from tvevents.api.models import ErrorResponse, IngestResponse
from tvevents.config import get_settings
from tvevents.deps import get_blacklist_cache, get_rds_client
from tvevents.domain.delivery import send_to_topics
from tvevents.domain.event_types import EVENT_TYPE_MAP
from tvevents.domain.obfuscation import obfuscate_output, should_obfuscate_channel
from tvevents.domain.transform import generate_output_json
from tvevents.domain.validation import TvEventsDefaultException, validate_request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=IngestResponse,
    responses={400: {"model": ErrorResponse}},
    summary="TV event ingestion",
    description="Receive, validate, transform, and deliver a TV event payload to Kafka.",
)
async def ingest(request: Request) -> Response:
    """Main ingestion endpoint — receives TV event JSON payload."""
    settings = get_settings()
    payload: dict = await request.json()

    tvid = request.query_params.get("tvid", "")
    event_type = request.query_params.get("event_type", "")

    url_params = {
        "tvid": tvid,
        "event_type": event_type,
    }

    try:
        validate_request(url_params, payload, settings.t1_salt, EVENT_TYPE_MAP)

        output_json = generate_output_json(payload, settings.zoo, EVENT_TYPE_MAP)

        cache = get_blacklist_cache()
        rds_client = get_rds_client()
        blacklisted_ids = cache.get_blacklisted_channel_ids(
            fetch_from_db=rds_client.fetch_blacklisted_channel_ids
        )

        if should_obfuscate_channel(output_json, blacklisted_ids):
            if settings.tvevents_debug:
                send_to_topics(output_json, settings.valid_debug_kafka_topics)

            logger.debug(
                "Obfuscating: tvid=%s, channel_id=%s, iscontentblocked=%s",
                output_json.get("tvid"),
                output_json.get("channelid"),
                output_json.get("iscontentblocked"),
            )
            obfuscate_output(output_json)

        send_to_topics(output_json, settings.valid_kafka_topics)

        return Response(
            content=IngestResponse(status="OK").model_dump_json(),
            status_code=200,
            media_type="application/json",
        )

    except TvEventsDefaultException as e:
        logger.error(
            "Validation error in ingest: tvid=%s msg=%s",
            tvid,
            e,
        )
        return Response(
            content=ErrorResponse(
                error=type(e).__name__, detail=str(e)
            ).model_dump_json(),
            status_code=e.status_code,
            media_type="application/json",
        )
    except Exception as e:
        logger.error(
            "Exception in ingest: tvid=%s msg=%s",
            tvid,
            e,
            exc_info=sys.exc_info(),
        )
        return Response(
            content=ErrorResponse(
                error="TvEventsCatchallException", detail=str(e)
            ).model_dump_json(),
            status_code=400,
            media_type="application/json",
        )


@router.get(
    "/status",
    summary="Health check (legacy compat)",
    description="Returns 'OK' for backward compatibility with Kubernetes probes.",
)
async def status() -> str:
    """Legacy health check — always returns OK."""
    return "OK"


@router.get(
    "/health",
    summary="Health check",
    description="Alias for /status.",
)
async def health() -> str:
    """Health check alias."""
    return "OK"
