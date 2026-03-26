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


class HealthResponse(BaseModel):
    """Application health check response."""

    status: Literal["ok", "degraded"]
    version: str
    mcp_tools: MCPToolsStatus


# ── Portfolio health schemas ─────────────────────────────────────────────────


class HealthComponent(BaseModel):
    """A single health score component."""

    name: str
    score: float  # 0-10
    weight: float  # 0-1
    detail: str


class PositionHealth(BaseModel):
    """Per-position contribution to portfolio health."""

    ticker: str
    weight_pct: float
    signal_score: float | None = None
    sector: str | None = None
    contribution: str  # "strength" or "drag"


class PortfolioHealthResult(BaseModel):
    """Complete portfolio health assessment."""

    health_score: float  # 0-10
    grade: str  # A+, A, B+, B, C+, C, D, F
    components: list[HealthComponent]
    metrics: dict  # hhi, effective_stocks, weighted_beta, weighted_sharpe, etc.
    top_concerns: list[str]
    top_strengths: list[str]
    position_details: list[PositionHealth]
