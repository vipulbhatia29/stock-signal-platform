"""Build an ObservabilityClient from settings — single place for target selection.

PR2b extends this with the InternalHTTPTarget branch. Extraction swaps DirectTarget
with ExternalHTTPTarget here.

``obs_client_var`` ContextVar + ``_maybe_get_obs_client()`` provide a layering-safe
lookup for domain modules (ObservabilityCollector, rate_limiter, etc.) that
need the client from either a FastAPI or Celery context.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

from backend.config import settings
from backend.observability.client import ObservabilityClient
from backend.observability.targets.direct import DirectTarget
from backend.observability.targets.internal_http import InternalHTTPTarget
from backend.observability.targets.memory import MemoryTarget

# Module-level ContextVar — set by FastAPI lifespan + Celery worker_ready.
# Default None means "observability not initialized yet" — emitters short-circuit
# silently (no exceptions past the domain module boundary).
obs_client_var: ContextVar[ObservabilityClient | None] = ContextVar("obs_client", default=None)


def build_client_from_settings() -> ObservabilityClient:
    """Construct an ObservabilityClient using current settings."""
    if settings.OBS_TARGET_TYPE == "memory":
        target = MemoryTarget()
    elif settings.OBS_TARGET_TYPE == "internal_http":
        if not settings.OBS_TARGET_URL or not settings.OBS_INGEST_SECRET:
            raise RuntimeError(
                "OBS_TARGET_TYPE=internal_http requires OBS_TARGET_URL + OBS_INGEST_SECRET"
            )
        target = InternalHTTPTarget(
            base_url=settings.OBS_TARGET_URL, secret=settings.OBS_INGEST_SECRET
        )
    else:  # "direct" (default)
        target = DirectTarget()
    return ObservabilityClient(
        target=target,
        spool_dir=Path(settings.OBS_SPOOL_DIR),
        spool_enabled=settings.OBS_SPOOL_ENABLED,
        flush_interval_ms=settings.OBS_FLUSH_INTERVAL_MS,
        buffer_size=settings.OBS_BUFFER_SIZE,
        enabled=settings.OBS_ENABLED,
        spool_max_size_mb=settings.OBS_SPOOL_MAX_SIZE_MB,
    )


def _maybe_get_obs_client() -> ObservabilityClient | None:
    """Look up the ambient client — FastAPI lifespan or Celery worker_ready sets it.

    Returns None if observability isn't initialized yet (e.g., during pytest fixtures
    that bypass lifespan). Callers MUST handle None gracefully — no exceptions leak
    out of emitter code paths.
    """
    return obs_client_var.get()
