"""POST /api/v1/observability/frontend-error — beacon endpoint for frontend JS errors.

Accepts batched error reports from the frontend observability-beacon library.
Auth is optional (pre-auth errors won't have a JWT). Rate limited at 10/min.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field

from backend.config import settings
from backend.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observability", tags=["observability"])


class FrontendErrorItem(BaseModel):
    """Single frontend error in a beacon batch."""

    error_type: str
    error_message: str | None = Field(default=None, max_length=1024)
    error_stack: str | None = Field(default=None, max_length=5120)
    page_route: str | None = None
    component_name: str | None = None
    url: str | None = None
    metadata: dict | None = None


class FrontendErrorPayload(BaseModel):
    """Batch of frontend errors submitted by the beacon library."""

    errors: list[FrontendErrorItem] = Field(max_length=10)


def _try_extract_user_id(request: Request) -> UUID | None:
    """Best-effort user_id extraction from JWT cookie. Returns None on any failure."""
    try:
        from backend.dependencies import COOKIE_ACCESS_TOKEN, decode_token

        token = request.cookies.get(COOKIE_ACCESS_TOKEN)
        if not token:
            return None
        payload = decode_token(token, expected_type="access")
        return payload.user_id
    except Exception:  # noqa: BLE001 — never fail on auth extraction
        return None


@router.post("/frontend-error", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def report_frontend_errors(
    request: Request,
    payload: FrontendErrorPayload,
) -> dict:
    """Accept a batch of frontend JavaScript errors.

    Auth is optional — pre-auth errors (login page crashes, etc.) are still
    captured. User ID is extracted from the JWT cookie when available.
    Trace ID is captured from the X-Trace-Id header (set by backend in 1a).

    Rate limited at 10 requests per minute per client IP.
    """
    user_id = _try_extract_user_id(request)
    trace_id_header = request.headers.get("X-Trace-Id")
    trace_id: UUID | None = None
    if trace_id_header:
        try:
            trace_id = UUID(trace_id_header)
        except ValueError:
            pass

    env = getattr(settings, "APP_ENV", "dev")

    # Emit each error via the SDK
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.schema.frontend_deploy_events import (
            FrontendErrorEvent,
            FrontendErrorType,
        )
        from backend.observability.schema.v1 import EventType

        obs_client = _maybe_get_obs_client()
        if obs_client:
            now = datetime.now(timezone.utc)
            for item in payload.errors:
                try:
                    error_type = FrontendErrorType(item.error_type)
                except ValueError:
                    error_type = FrontendErrorType.UNHANDLED_REJECTION

                event = FrontendErrorEvent(
                    event_type=EventType.FRONTEND_ERROR,
                    trace_id=trace_id or uuid4(),
                    span_id=uuid4(),
                    parent_span_id=None,
                    ts=now,
                    env=env,
                    git_sha=None,
                    user_id=user_id,
                    session_id=None,
                    query_id=None,
                    error_type=error_type,
                    error_message=item.error_message,
                    error_stack=item.error_stack,
                    page_route=item.page_route,
                    component_name=item.component_name,
                    user_agent=request.headers.get("User-Agent"),
                    url=item.url,
                    frontend_metadata=item.metadata,
                )
                await obs_client.emit(event)
    except Exception:  # noqa: BLE001 — fire-and-forget, never block the beacon
        logger.warning("obs.frontend_error.emit_failed", exc_info=True)

    return {"accepted": len(payload.errors)}
