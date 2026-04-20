"""MCP tool: describe_observability_schema.

Returns a full self-description of the observability schema — tables, enums,
event types, and the tool manifest.  Agents call this at session start so they
know what is queryable without requiring any prior schema knowledge.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.database import async_session_factory
from backend.observability.mcp._helpers import build_envelope
from backend.observability.schema.v1 import AttributionLayer, EventType, Severity

# ---------------------------------------------------------------------------
# Static schema metadata — update when migrations add/remove tables
# ---------------------------------------------------------------------------

_OBS = "observability"

_TABLES = [
    {"name": "request_log", "schema": _OBS, "retention_days": 30, "hypertable": True},
    {"name": "api_error_log", "schema": _OBS, "retention_days": 30, "hypertable": True},
    {
        "name": "external_api_call_log",
        "schema": _OBS,
        "retention_days": 30,
        "hypertable": True,
    },
    {"name": "rate_limiter_event", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "auth_event_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "oauth_event_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "email_send_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "slow_query_log", "schema": _OBS, "retention_days": 30, "hypertable": True},
    {"name": "db_pool_event", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {
        "name": "schema_migration_log",
        "schema": _OBS,
        "retention_days": 365,
        "hypertable": False,
    },
    {"name": "cache_operation_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {
        "name": "celery_worker_heartbeat",
        "schema": _OBS,
        "retention_days": 1,
        "hypertable": False,
    },
    {"name": "beat_schedule_run", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "celery_queue_depth", "schema": _OBS, "retention_days": 7, "hypertable": False},
    {"name": "agent_intent_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "agent_reasoning_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {
        "name": "provider_health_snapshot",
        "schema": _OBS,
        "retention_days": 7,
        "hypertable": False,
    },
    {"name": "frontend_error_log", "schema": _OBS, "retention_days": 30, "hypertable": False},
    {"name": "deploy_events", "schema": _OBS, "retention_days": 365, "hypertable": False},
    {"name": "finding_log", "schema": _OBS, "retention_days": 180, "hypertable": False},
    {"name": "llm_call_log", "schema": "public", "retention_days": 30, "hypertable": True},
    {"name": "tool_execution_log", "schema": "public", "retention_days": 30, "hypertable": True},
    {"name": "pipeline_runs", "schema": "public", "retention_days": 90, "hypertable": False},
    {"name": "dq_check_history", "schema": "public", "retention_days": 90, "hypertable": False},
]

_TOOL_MANIFEST = [
    {
        "name": "describe_observability_schema",
        "description": "Self-describing schema — tables, enums, event types, tool manifest",
    },
    {
        "name": "get_platform_health",
        "description": "System-wide health snapshot — per-subsystem status, open anomalies",
    },
    {
        "name": "get_trace",
        "description": "Full cross-layer trace reconstruction as span tree",
    },
    {
        "name": "get_recent_errors",
        "description": "Filtered error stream across all subsystems",
    },
    {
        "name": "get_anomalies",
        "description": "Open anomaly findings ranked by severity",
    },
    {
        "name": "get_external_api_stats",
        "description": "Per-provider call stats with comparison window",
    },
    {
        "name": "get_dq_findings",
        "description": "Data quality scanner findings",
    },
    {
        "name": "diagnose_pipeline",
        "description": "Pipeline deep-dive — recent runs, failure patterns",
    },
    {
        "name": "get_slow_queries",
        "description": "Slow queries grouped by query_hash with baseline comparison",
    },
    {
        "name": "get_cost_breakdown",
        "description": "LLM cost trends by provider/model/tier/user",
    },
    {
        "name": "search_errors",
        "description": "Text search across error messages and finding titles",
    },
    {
        "name": "get_deploys",
        "description": "Recent deployments — SHA, PR, migrations, outcome",
    },
    {
        "name": "get_observability_health",
        "description": (
            "Self-observability — last-write timestamps, spool size, retention compliance"
        ),
    },
]


async def describe_observability_schema() -> dict[str, Any]:
    """Return a full self-description of the observability schema.

    Queries the DB for the active schema version and combines it with static
    metadata about tables, enums, and tool capabilities.  Agents should call
    this tool once at session start.

    Returns:
        Standard MCP envelope with schema_version, event_types,
        attribution_layers, severities, tables, and tool_manifest.
    """
    async with async_session_factory() as db:
        schema_version = (
            await db.execute(
                text(
                    "SELECT version FROM observability.schema_versions"
                    " ORDER BY applied_at DESC LIMIT 1"
                )
            )
        ).scalar()

    result: dict[str, Any] = {
        "schema_version": schema_version or "unknown",
        "event_types": [e.value for e in EventType],
        "attribution_layers": [a.value for a in AttributionLayer],
        "severities": [s.value for s in Severity],
        "tables": _TABLES,
        "tool_manifest": _TOOL_MANIFEST,
    }
    return build_envelope("describe_observability_schema", result)
