"""Pydantic v2 schemas for the health endpoint."""

from typing import Literal

from pydantic import BaseModel


class MCPToolsStatus(BaseModel):
    """MCP tool server subprocess status."""

    enabled: bool
    mode: Literal["stdio", "fallback_direct", "direct", "disabled"]
    healthy: bool
    tool_count: int
    restarts: int = 0
    uptime_seconds: float | None = None
    last_error: str | None = None
    fallback_since: str | None = None


class DependencyStatus(BaseModel):
    """Status of a backend dependency (database, Redis, etc.)."""

    healthy: bool
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Application health check response."""

    status: Literal["ok", "degraded"]
    version: str
    redis: DependencyStatus
    database: DependencyStatus
    mcp_tools: MCPToolsStatus
