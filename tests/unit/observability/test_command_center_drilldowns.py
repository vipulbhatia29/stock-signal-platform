"""Unit tests for Command Center drill-down endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.routers.command_center import (
    get_api_traffic_detail,
    get_llm_detail,
    get_pipeline_detail,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_user() -> MagicMock:
    """Return a mock admin user that passes require_admin."""
    user = MagicMock()
    user.role = "admin"
    return user


# ---------------------------------------------------------------------------
# GET /api-traffic tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_traffic_detail_no_collector() -> None:
    """Returns unavailable status when http_metrics is absent from app state."""
    request = MagicMock()
    request.app.state = MagicMock(spec=[])  # no http_metrics

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_api_traffic_detail(hours=24, user=_admin_user(), request=request)

    assert result["status"] == "unavailable"
    assert result["endpoints"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_api_traffic_detail_with_data() -> None:
    """Returns full traffic data when http_metrics is available."""
    mock_metrics = AsyncMock()
    mock_metrics.get_stats.return_value = {
        "window_seconds": 300,
        "sample_count": 120,
        "total_requests_today": 5000,
        "total_errors_today": 25,
        "latency_p50_ms": 8.5,
        "latency_p95_ms": 42.0,
        "latency_p99_ms": 95.0,
        "error_rate_pct": 0.5,
        "top_endpoints": [
            {"endpoint": "GET:/api/v1/health", "count": 200},
            {"endpoint": "POST:/api/v1/chat", "count": 150},
        ],
    }

    request = MagicMock()
    request.app.state.http_metrics = mock_metrics

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_api_traffic_detail(hours=48, user=_admin_user(), request=request)

    assert result["window_seconds"] == 300
    assert result["sample_count"] == 120
    assert result["total_requests_today"] == 5000
    assert result["total_errors_today"] == 25
    assert result["latency_p50_ms"] == 8.5
    assert result["latency_p95_ms"] == 42.0
    assert result["latency_p99_ms"] == 95.0
    assert result["error_rate_pct"] == 0.5
    assert len(result["endpoints"]) == 2


# ---------------------------------------------------------------------------
# GET /llm tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_detail_returns_models() -> None:
    """Returns per-model breakdown from LLMCallLog rows."""
    # Mock DB row objects
    model_row = MagicMock()
    model_row.model = "llama-3.3-70b"
    model_row.provider = "groq"
    model_row.call_count = 42
    model_row.total_cost = 0.0123
    model_row.avg_latency_ms = 350.5
    model_row.error_count = 2
    model_row.total_prompt_tokens = 10000
    model_row.total_completion_tokens = 5000

    cascade_row = MagicMock()
    cascade_row.model = "llama-3.3-70b"
    cascade_row.error = "rate_limit_exceeded"
    cascade_row.created_at = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)

    db = AsyncMock()
    # First call: model breakdown query
    # Second call: cascade query
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[model_row])),
            MagicMock(all=MagicMock(return_value=[cascade_row])),
        ]
    )

    request = MagicMock()

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_llm_detail(hours=24, user=_admin_user(), db=db, request=request)

    assert result["hours"] == 24
    assert result["total_models"] == 1
    assert result["models"][0]["model"] == "llama-3.3-70b"
    assert result["models"][0]["provider"] == "groq"
    assert result["models"][0]["call_count"] == 42
    assert result["models"][0]["total_cost_usd"] == 0.0123
    assert result["models"][0]["avg_latency_ms"] == 350.5
    assert result["models"][0]["error_count"] == 2
    assert result["models"][0]["total_prompt_tokens"] == 10000
    assert result["models"][0]["total_completion_tokens"] == 5000
    assert len(result["cascades"]) == 1
    assert result["cascades"][0]["error"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_llm_detail_empty() -> None:
    """Returns empty models list when no LLMCallLog rows exist."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[])),  # no model rows
            MagicMock(all=MagicMock(return_value=[])),  # no cascade rows
        ]
    )

    request = MagicMock()

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_llm_detail(hours=24, user=_admin_user(), db=db, request=request)

    assert result["hours"] == 24
    assert result["total_models"] == 0
    assert result["models"] == []
    assert result["cascades"] == []


# ---------------------------------------------------------------------------
# GET /pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("backend.observability.routers.command_center.get_run_history")
async def test_pipeline_detail_returns_runs(mock_history: AsyncMock) -> None:
    """Returns run history list from get_run_history."""
    mock_history.return_value = [
        {
            "id": "run-1",
            "status": "completed",
            "started_at": "2026-03-31T21:30:00+00:00",
            "duration_seconds": 1800,
            "tickers_total": 100,
        },
        {
            "id": "run-2",
            "status": "failed",
            "started_at": "2026-03-30T21:30:00+00:00",
            "duration_seconds": 900,
            "tickers_total": 50,
        },
    ]

    db = AsyncMock()

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_pipeline_detail(days=7, user=_admin_user(), db=db)

    assert result["days"] == 7
    assert result["total"] == 2
    assert len(result["runs"]) == 2
    assert result["runs"][0]["status"] == "completed"
    assert result["runs"][1]["status"] == "failed"
    mock_history.assert_awaited_once_with(db, days=7)


@pytest.mark.asyncio
@patch("backend.observability.routers.command_center.get_run_history")
async def test_pipeline_detail_empty(mock_history: AsyncMock) -> None:
    """Returns total=0 when no pipeline runs exist."""
    mock_history.return_value = []

    db = AsyncMock()

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_pipeline_detail(days=14, user=_admin_user(), db=db)

    assert result["days"] == 14
    assert result["total"] == 0
    assert result["runs"] == []
    mock_history.assert_awaited_once_with(db, days=14)
