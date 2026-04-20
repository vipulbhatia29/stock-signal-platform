"""FastMCP registration for observability MCP tools."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


def create_obs_mcp_app() -> FastMCP:
    """Create a FastMCP server with all 13 observability tools.

    Returns:
        Configured FastMCP instance.
    """
    mcp = FastMCP("Observability Intelligence")

    # Import tools lazily to avoid circular imports
    from backend.observability.mcp.anomalies import get_anomalies
    from backend.observability.mcp.cost_breakdown import get_cost_breakdown
    from backend.observability.mcp.deploys import get_deploys
    from backend.observability.mcp.describe_schema import describe_observability_schema
    from backend.observability.mcp.diagnose_pipeline import diagnose_pipeline
    from backend.observability.mcp.dq_findings import get_dq_findings
    from backend.observability.mcp.external_api_stats import get_external_api_stats
    from backend.observability.mcp.obs_health import get_observability_health
    from backend.observability.mcp.platform_health import get_platform_health
    from backend.observability.mcp.recent_errors import get_recent_errors
    from backend.observability.mcp.search_errors import search_errors
    from backend.observability.mcp.slow_queries import get_slow_queries
    from backend.observability.mcp.trace import get_trace

    _TOOLS = [
        (
            "describe_observability_schema",
            "Self-describing schema — tables, enums, event types, tool manifest",
            describe_observability_schema,
        ),
        (
            "get_platform_health",
            "System-wide health snapshot — per-subsystem status, open anomalies",
            get_platform_health,
        ),
        (
            "get_trace",
            "Full cross-layer trace reconstruction as span tree",
            get_trace,
        ),
        (
            "get_recent_errors",
            "Filtered error stream across all subsystems",
            get_recent_errors,
        ),
        (
            "get_anomalies",
            "Open anomaly findings ranked by severity",
            get_anomalies,
        ),
        (
            "get_external_api_stats",
            "Per-provider call stats with comparison window",
            get_external_api_stats,
        ),
        (
            "get_dq_findings",
            "Data quality scanner findings",
            get_dq_findings,
        ),
        (
            "diagnose_pipeline",
            "Pipeline deep-dive — recent runs, failure patterns",
            diagnose_pipeline,
        ),
        (
            "get_slow_queries",
            "Slow queries grouped by query_hash with baseline comparison",
            get_slow_queries,
        ),
        (
            "get_cost_breakdown",
            "LLM cost trends by provider/model/tier/user",
            get_cost_breakdown,
        ),
        (
            "search_errors",
            "Text search across error messages and finding titles",
            search_errors,
        ),
        (
            "get_deploys",
            "Recent deployments — SHA, PR, migrations, outcome",
            get_deploys,
        ),
        (
            "get_observability_health",
            "Self-observability — last-write timestamps, spool size, retention compliance",
            get_observability_health,
        ),
    ]

    for name, desc, fn in _TOOLS:
        mcp.tool(name=name, description=desc)(fn)

    logger.info("Observability MCP server created with %d tools", len(_TOOLS))
    return mcp
