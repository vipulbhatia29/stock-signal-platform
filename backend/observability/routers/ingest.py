"""POST /obs/v1/events — ingest endpoint for InternalHTTPTarget / future ExternalHTTPTarget."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from backend.config import settings
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.service.event_writer import write_batch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability-ingest"])

MAX_EVENTS_PER_BATCH = 500


class IngestBatch(BaseModel):
    """Batch of events submitted to the ingest endpoint."""

    events: list[ObsEventBase]
    schema_version: str


@router.post("/obs/v1/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    batch: IngestBatch,
    x_obs_secret: str | None = Header(default=None, alias="X-Obs-Secret"),
) -> dict[str, int]:
    """Accept a batch of observability events.

    Validates shared-secret auth, batch size, and schema version before
    delegating to the event writer.
    """
    # Fail-closed: no secret configured means no one can POST.
    if not settings.OBS_INGEST_SECRET or x_obs_secret != settings.OBS_INGEST_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Obs-Secret",
        )
    if len(batch.events) > MAX_EVENTS_PER_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"batch size {len(batch.events)} exceeds max {MAX_EVENTS_PER_BATCH}",
        )
    if batch.schema_version != "v1":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unsupported schema_version",
        )
    try:
        await write_batch(batch.events)
    except Exception:  # noqa: BLE001 — surface via 503 for client retry
        logger.exception("obs.ingest.writer_failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event_writer_failure",
        )
    return {"accepted": len(batch.events)}
