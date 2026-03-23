"""Health check endpoint with MCP subprocess status."""

from fastapi import APIRouter, Request

from backend.config import settings
from backend.schemas.health import HealthResponse, MCPToolsStatus

router = APIRouter()

_APP_VERSION = "0.1.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application health check",
    description="Returns application status including MCP tool server subprocess health.",
)
async def health_check(request: Request) -> HealthResponse:
    """Return application health with MCP subprocess status."""
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

    app_status = "degraded" if mcp_status.enabled and not mcp_status.healthy else "ok"

    return HealthResponse(
        status=app_status,
        version=_APP_VERSION,
        mcp_tools=mcp_status,
    )
