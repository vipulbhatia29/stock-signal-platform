"""POST /obs/v1/events — ingest endpoint for InternalHTTPTarget / future ExternalHTTPTarget."""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.config import settings
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.service.event_writer import write_batch
from backend.observability.targets.internal_http import OBS_SECRET_HEADER

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability-ingest"])

OBS_INGEST_PATH = "/obs/v1/events"
MAX_EVENTS_PER_BATCH = 500

_AUTH_HEADERS = {"WWW-Authenticate": OBS_SECRET_HEADER}


class IngestBatch(BaseModel):
    """Batch of events submitted to the ingest endpoint."""

    events: Annotated[list[ObsEventBase], Field(min_length=1)]
    schema_version: Literal["v1"]


class IngestResponse(BaseModel):
    """Response from the ingest endpoint."""

    accepted: int


@router.post(
    OBS_INGEST_PATH,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestResponse,
)
async def ingest_events(
    batch: IngestBatch,
    x_obs_secret: str | None = Header(default=None, alias=OBS_SECRET_HEADER),
) -> IngestResponse:
    """Accept a batch of observability events.

    Validates shared-secret auth and batch size before delegating to
    the event writer.
    """
    # Fail-closed: no secret configured means no one can POST.
    if not settings.OBS_INGEST_SECRET or not x_obs_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers=_AUTH_HEADERS,
        )
    if not hmac.compare_digest(x_obs_secret, settings.OBS_INGEST_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers=_AUTH_HEADERS,
        )
    if len(batch.events) > MAX_EVENTS_PER_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="batch too large",
        )
    try:
        await write_batch(batch.events)
    except Exception:  # noqa: BLE001 — surface via 503 for client retry
        logger.exception("obs.ingest.writer_failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event_writer_failure",
            headers={"Retry-After": "5"},
        )
    return IngestResponse(accepted=len(batch.events))
