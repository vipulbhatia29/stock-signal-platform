"""Health check endpoints.

Two tiers:
- GET /health          — public, returns only status + version.
- GET /health/detail   — authenticated, returns full dependency details.
"""

import logging
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from backend.config import settings
from backend.database import async_session_factory
from backend.dependencies import get_current_user
from backend.schemas.health import (
    DependencyStatus,
    HealthResponse,
    HealthStatusResponse,
    MCPToolsStatus,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_APP_VERSION = "0.1.0"


async def _check_redis(request: Request) -> DependencyStatus:
    """Ping Redis and return connectivity status."""
    cache_service = getattr(request.app.state, "cache", None)
    if cache_service is None:
        return DependencyStatus(healthy=False, error="Redis not initialized")
    try:
        start = time.monotonic()
        await cache_service._redis.ping()
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(healthy=True, latency_ms=round(latency, 2))
    except Exception:
        logger.warning("Redis health check failed", exc_info=True)
        return DependencyStatus(healthy=False, error="Redis connection failed")


async def _check_database() -> DependencyStatus:
    """Execute SELECT 1 and return DB connectivity status."""
    try:
        start = time.monotonic()
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        latency = (time.monotonic() - start) * 1000
        return DependencyStatus(healthy=True, latency_ms=round(latency, 2))
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        return DependencyStatus(healthy=False, error="Database connection failed")


async def _compute_status(request: Request) -> str:
    """Check all dependencies and return 'ok' or 'degraded'.

    Args:
        request: The incoming FastAPI request (used to access app state).

    Returns:
        'ok' when all core services are healthy, 'degraded' otherwise.
    """
    redis_status = await _check_redis(request)
    db_status = await _check_database()

    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    if settings.MCP_TOOLS and mcp_manager is not None:
        mcp_degraded = not mcp_manager.healthy
    else:
        mcp_degraded = False

    any_degraded = not redis_status.healthy or not db_status.healthy or mcp_degraded
    return "degraded" if any_degraded else "ok"


@router.get(
    "/health",
    response_model=HealthStatusResponse,
    summary="Public application health check",
    description="Status and version only — safe for load balancers.",
)
async def health_check(request: Request) -> HealthStatusResponse:
    """Return minimal health status without exposing internal dependency details.

    Args:
        request: The incoming FastAPI request (used to access app state).

    Returns:
        HealthStatusResponse with status and version only.
    """
    app_status = await _compute_status(request)
    return HealthStatusResponse(status=app_status, version=_APP_VERSION)


@router.get(
    "/health/detail",
    response_model=HealthResponse,
    summary="Detailed application health check (authenticated)",
    description="Full dependency details (Redis, DB, MCP). Requires authentication.",
)
async def health_check_detail(
    request: Request,
    _current_user: object = Depends(get_current_user),
) -> HealthResponse:
    """Return full health details including Redis, DB, and MCP subprocess status.

    Requires a valid JWT. Only authenticated users may see internal state.

    Args:
        request: The incoming FastAPI request (used to access app state).
        _current_user: Injected by get_current_user; raises 401 if not authenticated.

    Returns:
        HealthResponse with Redis, database, and MCP tool details.
    """
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    registry = getattr(request.app.state, "registry", None)
    tool_count = len(registry.discover()) if registry else 0

    if not settings.MCP_TOOLS:
        mcp_status = MCPToolsStatus(
            enabled=False,
            mode="direct",
            healthy=True,
            tool_count=tool_count,
        )
    elif mcp_manager is None:
        mcp_status = MCPToolsStatus(
            enabled=True,
            mode="disabled",
            healthy=False,
            tool_count=tool_count,
        )
    else:
        mcp_status = MCPToolsStatus(
            enabled=True,
            mode=mcp_manager.mode,
            healthy=mcp_manager.healthy,
            tool_count=tool_count,
            restarts=mcp_manager.restart_count,
            uptime_seconds=mcp_manager.uptime_seconds,
            last_error=mcp_manager.last_error,
            fallback_since=mcp_manager.fallback_since,
        )

    redis_status = await _check_redis(request)
    db_status = await _check_database()

    mcp_degraded = mcp_status.enabled and not mcp_status.healthy
    any_degraded = not redis_status.healthy or not db_status.healthy or mcp_degraded
    app_status = "degraded" if any_degraded else "ok"

    return HealthResponse(
        status=app_status,
        version=_APP_VERSION,
        redis=redis_status,
        database=db_status,
        mcp_tools=mcp_status,
    )
