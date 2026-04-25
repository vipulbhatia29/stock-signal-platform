"""Integration tests: MCP tool functions return correct structures from real data.

Each MCP tool wraps results in a standard envelope via build_envelope():
    {"tool": str, "window": {...}, "result": {...}, "meta": {...}}
Tests navigate the envelope to assert on the inner result dict (H7: exact keys).
"""

import uuid

import pytest

from tests.integration.observability.conftest import (
    ApiErrorLogFactory,
    ExternalApiCallFactory,
    FindingLogFactory,
    RequestLogFactory,
    insert_obs_rows,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_platform_health_structure(obs_db_session, _patch_session_factory):
    """get_platform_health() returns envelope with overall_status + subsystems dict."""
    from backend.observability.mcp.platform_health import get_platform_health

    await insert_obs_rows(obs_db_session, [RequestLogFactory.build() for _ in range(5)])
    envelope = await get_platform_health(window_min=60)

    assert envelope["tool"] == "get_platform_health"
    result = envelope["result"]
    assert result["overall_status"] in ("healthy", "degraded", "failing")
    assert "subsystems" in result
    assert "open_anomaly_count" in result
    assert envelope["meta"]["schema_version"] == "v1"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_trace_reconstructs_spans(obs_db_session, _patch_session_factory):
    """get_trace() returns envelope with trace_id + span_count from multi-table data."""
    from backend.observability.mcp.trace import get_trace

    shared_trace = str(uuid.uuid4())
    rows = [
        RequestLogFactory.build(trace_id=shared_trace),
        ExternalApiCallFactory.build(trace_id=shared_trace),
    ]
    await insert_obs_rows(obs_db_session, rows)

    envelope = await get_trace(trace_id=shared_trace)

    assert envelope["tool"] == "get_trace"
    result = envelope["result"]
    assert result["trace_id"] == shared_trace
    assert result["span_count"] >= 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_anomalies_returns_findings(obs_db_session, _patch_session_factory):
    """get_anomalies() returns envelope with findings list filtered by severity."""
    from backend.observability.mcp.anomalies import get_anomalies

    await insert_obs_rows(
        obs_db_session,
        [
            FindingLogFactory.build(severity="CRITICAL", status="open"),
            FindingLogFactory.build(severity="WARNING", status="open"),
        ],
    )
    envelope = await get_anomalies(status="open", severity="CRITICAL")

    result = envelope["result"]
    assert "findings" in result
    assert len(result["findings"]) >= 1
    assert all(f["severity"] == "CRITICAL" for f in result["findings"])
    assert envelope["meta"]["total_count"] >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_errors_text_match(obs_db_session, _patch_session_factory):
    """search_errors() returns envelope with matches list containing source + matched_text."""
    from backend.observability.mcp.search_errors import search_errors

    await insert_obs_rows(
        obs_db_session,
        [ApiErrorLogFactory.build(error_message="connection timeout to yfinance")],
    )
    envelope = await search_errors(query="timeout", since="1h", limit=10)

    assert envelope["tool"] == "search_errors"
    result = envelope["result"]
    assert "matches" in result
    assert len(result["matches"]) >= 1
    assert "source" in result["matches"][0]
    assert "matched_text" in result["matches"][0]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_obs_health_self_report(_patch_session_factory):
    """get_observability_health() returns envelope with last_writes + config keys."""
    from backend.observability.mcp.obs_health import get_observability_health

    envelope = await get_observability_health()

    assert envelope["tool"] == "get_observability_health"
    result = envelope["result"]
    assert "last_writes" in result
    assert "config" in result
    assert isinstance(result["config"]["OBS_ENABLED"], bool)
