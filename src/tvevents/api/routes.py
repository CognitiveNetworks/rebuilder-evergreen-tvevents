"""Event ingestion route — ``POST /v1/events``.

Mirrors the legacy Flask ``POST /`` route with the exact same:
1. Validation pipeline (required params → param match → timestamp → HMAC → event-type)
2. Output JSON generation (flatten + event-type-specific transforms)
3. Obfuscation check (iscontentblocked / blacklist)
4. Delivery to Kafka (replaces Firehose)
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, Request
from opentelemetry import trace

from tvevents.api.models import ErrorResponse, EventIngestionResponse
from tvevents.domain.event_types import generate_output_json
from tvevents.domain.obfuscation import obfuscate_output, should_obfuscate_channel
from tvevents.domain.validation import validate_request

if TYPE_CHECKING:
    from tvevents.config import Settings

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(prefix="/v1", tags=["events"])


@router.post(
    "/events",
    response_model=EventIngestionResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Ingest a TV event",
)
async def ingest_event(
    request: Request,
    tvid: str | None = Query(default=None, description="TV identifier from URL"),
    event_type: str | None = Query(default=None, description="Event type from URL"),
) -> EventIngestionResponse:
    """Receive a TV event payload, validate, transform, and deliver to Kafka.

    The request body must contain ``TvEvent`` (envelope) and ``EventData``
    (event-type-specific payload).  Query parameters ``tvid`` and
    ``event_type`` are cross-checked against the body fields for parity
    with the legacy endpoint.
    """
    event_id = str(uuid.uuid4())
    state = request.app.state
    settings: Settings = state.settings

    with tracer.start_as_current_span("ingest_event") as span:
        span.set_attribute("event_id", event_id)
        span.set_attribute("tvid", tvid or "")
        span.set_attribute("event_type", event_type or "unknown")

        payload: dict[str, Any] = await request.json()

        logger.info(
            "Received event: tvid=%s event_type=%s event_id=%s",
            tvid,
            event_type,
            event_id,
        )

        # ── URL params dict (legacy compat) ──────────────────────────
        url_params: dict[str, Any] = {"tvid": tvid, "event_type": event_type}

        # ── Validate ─────────────────────────────────────────────────
        validate_request(url_params, payload, settings.t1_salt)

        # ── Generate output JSON ─────────────────────────────────────
        output_json = generate_output_json(payload, zoo=settings.zoo)

        # ── Obfuscation check ────────────────────────────────────────
        cache_service = state.cache
        obfuscated = await should_obfuscate_channel(output_json, cache_service)

        if obfuscated:
            # If debug mode, send un-obfuscated version to debug topic first
            if settings.tvevents_debug:
                kafka = state.kafka
                if kafka is not None and settings.kafka_delivery_enabled:
                    await kafka.send(
                        topic=settings.kafka_debug_topic,
                        data=output_json,
                        key=tvid,
                    )

            logger.debug(
                "Obfuscating: tvid=%s channel_id=%s iscontentblocked=%s",
                output_json.get("tvid"),
                output_json.get("channelid"),
                output_json.get("iscontentblocked"),
            )
            obfuscate_output(output_json)

        # ── Deliver to Kafka ─────────────────────────────────────────
        kafka = state.kafka
        if kafka is not None and settings.kafka_delivery_enabled:
            await kafka.send(
                topic=settings.kafka_topic,
                data=output_json,
                key=tvid,
            )
            logger.debug("Event delivered to Kafka: %s", json.dumps(output_json))

        resolved_event_type: str = payload.get("TvEvent", {}).get("EventType", "unknown")
        return EventIngestionResponse(
            status="accepted",
            event_id=event_id,
            event_type=resolved_event_type,
        )
