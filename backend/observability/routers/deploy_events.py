"""POST /api/v1/observability/deploy-event — webhook for CI/CD deploy events.

Authenticated via OBS_DEPLOY_WEBHOOK_SECRET (Bearer token).
Deploy events are low volume (~1-5/day) and written directly to the DB,
not routed through the SDK.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status

from backend.config import settings
from backend.database import async_session_factory
from backend.observability.instrumentation.db import _in_obs_write
from backend.observability.schema.frontend_deploy_events import DeployEventData
from backend.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observability", tags=["observability"])


@router.post("/deploy-event", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def record_deploy_event(
    request: Request,
    payload: DeployEventData,
    authorization: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    """Record a deployment event from GitHub Actions.

    Authentication:
    - Primary: Authorization header must be ``Bearer <OBS_DEPLOY_WEBHOOK_SECRET>``
      validated with ``secrets.compare_digest`` (constant-time).
    - Secondary: X-GitHub-Event header checked as additional context.

    Deploy events are written directly to the deploy_events table (not via SDK)
    because they are very low volume and benefit from synchronous error feedback.

    Raises:
        HTTPException: 401 if secret is missing/invalid, 503 on write failure.
    """
    # --- Auth: validate webhook secret ---
    configured_secret = settings.OBS_DEPLOY_WEBHOOK_SECRET
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="deploy webhook not configured",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_secret = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided_secret, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Secondary check: X-GitHub-Event header ---
    if not x_github_event:
        logger.warning("obs.deploy_event.missing_github_header")
    elif x_github_event != "deployment":
        logger.warning(
            "obs.deploy_event.unexpected_github_header",
            extra={"x_github_event": x_github_event},
        )

    # --- Write directly to DB ---
    # Lazy import to avoid registering obs-schema models in SQLAlchemy metadata
    # at app startup (breaks tests that don't have the observability schema).
    from backend.observability.models.deploy_events import DeployEvent

    token = _in_obs_write.set(True)
    try:
        async with async_session_factory() as session:
            session.add(
                DeployEvent(
                    ts=payload.ts or datetime.now(timezone.utc),
                    git_sha=payload.git_sha,
                    branch=payload.branch,
                    pr_number=payload.pr_number,
                    author=payload.author,
                    commit_message=payload.commit_message,
                    migrations_applied=payload.migrations_applied,
                    env=payload.env,
                    deploy_duration_seconds=payload.deploy_duration_seconds,
                    status=payload.status.value,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — surface via 503 for client retry
        logger.exception("obs.deploy_event.write_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event write failure",
            headers={"Retry-After": "5"},
        )
    finally:
        _in_obs_write.reset(token)

    logger.info(
        "Deploy event recorded: %s %s (%s)",
        payload.git_sha[:8],
        payload.branch,
        payload.status.value,
    )
    return {"status": "created", "git_sha": payload.git_sha}
