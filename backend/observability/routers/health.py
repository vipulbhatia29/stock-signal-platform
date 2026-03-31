"""Health check endpoint with Redis, DB, and MCP subprocess status."""

import logging
import time

from fastapi import APIRouter, Request
from sqlalchemy import text

from backend.config import settings
from backend.database import async_session_factory
from backend.schemas.health import DependencyStatus, HealthResponse, MCPToolsStatus

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


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description="Returns application status including Redis, database, and MCP tool server health.",
)
async def health_check(request: Request) -> HealthResponse:
    """Return application health with Redis, DB, and MCP subprocess status."""
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    registry = getattr(request.app.state, "registry", None)
    tool_count = len(registry.discover()) if registry else 0

    if not settings.MCP_TOOLS:
        # MCP disabled via kill switch
        mcp_status = MCPToolsStatus(
            enabled=False,
            mode="direct",
            healthy=True,
            tool_count=tool_count,
        )
    elif mcp_manager is None:
        # MCP enabled but manager not created (startup failure)
        mcp_status = MCPToolsStatus(
            enabled=True,
            mode="disabled",
            healthy=False,
            tool_count=tool_count,
        )
    else:
        # MCP enabled with active manager
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

    # "ok" only when all core services are healthy; MCP is non-critical when disabled
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
