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


def _admin_user() -> MagicMock:
    """Create a mock admin user."""
    user = MagicMock()
    user.role.value = "admin"
    return user


def _mock_request(**state_attrs: object) -> MagicMock:
    """Create a mock Request with app.state attributes."""
    request = MagicMock()
    state = MagicMock()
    for k, v in state_attrs.items():
        setattr(state, k, v)
    # Remove attributes not explicitly set
    if "http_metrics" not in state_attrs:
        del state.http_metrics
    request.app.state = state
    return request


# ---------------------------------------------------------------------------
# GET /api-traffic tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_traffic_detail_no_collector() -> None:
    """Returns unavailable status when http_metrics is absent from app state."""
    request = _mock_request()

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_api_traffic_detail(request=request, user=_admin_user())

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
            {"endpoint": "GET:/api/v1/stocks", "count": 200},
            {"endpoint": "POST:/api/v1/chat", "count": 150},
        ],
    }
    request = _mock_request(http_metrics=mock_metrics)

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_api_traffic_detail(request=request, user=_admin_user())

    assert result["window_seconds"] == 300
    assert result["sample_count"] == 120
    assert result["total_requests_today"] == 5000
    assert result["total_errors_today"] == 25
    assert result["latency_p50_ms"] == 8.5


# ---------------------------------------------------------------------------
# GET /llm tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_detail_returns_models() -> None:
    """Returns per-model breakdown with cost and cascade log."""
    model_row = MagicMock()
    model_row.model = "llama-3.3-70b"
    model_row.provider = "groq"
    model_row.call_count = 50
    model_row.total_cost = 0.05
    model_row.avg_latency_ms = 120.5
    model_row.error_count = 2
    model_row.total_prompt_tokens = 5000
    model_row.total_completion_tokens = 2000

    cascade_row = MagicMock()
    cascade_row.model = "llama-3.3-70b"
    cascade_row.error = "rate_limit_exceeded"
    cascade_row.created_at = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[model_row])),
            MagicMock(all=MagicMock(return_value=[cascade_row])),
        ]
    )

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_llm_detail(hours=24, user=_admin_user(), db=db)

    assert result["hours"] == 24
    assert result["total_models"] == 1
    assert result["models"][0]["model"] == "llama-3.3-70b"
    assert result["models"][0]["provider"] == "groq"
    assert result["cascades"][0]["error"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_llm_detail_empty() -> None:
    """Returns empty lists when no LLM data exists."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[])),
            MagicMock(all=MagicMock(return_value=[])),
        ]
    )

    with patch("backend.observability.routers.command_center.require_admin"):
        result = await get_llm_detail(hours=24, user=_admin_user(), db=db)

    assert result["hours"] == 24
    assert result["total_models"] == 0
    assert result["models"] == []
    assert result["cascades"] == []


# ---------------------------------------------------------------------------
# GET /pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_detail_returns_runs() -> None:
    """Returns pipeline run history."""
    mock_runs = [
        {"id": "abc", "status": "success", "started_at": "2026-03-31T00:00:00"},
        {"id": "def", "status": "partial", "started_at": "2026-03-30T00:00:00"},
    ]

    with (
        patch("backend.observability.routers.command_center.require_admin"),
        patch(
            "backend.observability.routers.command_center.get_run_history",
            return_value=mock_runs,
        ),
    ):
        result = await get_pipeline_detail(days=7, user=_admin_user(), db=AsyncMock())

    assert result["total"] == 2
    assert result["days"] == 7
    assert result["runs"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_pipeline_detail_empty() -> None:
    """Returns empty list when no pipeline runs exist."""
    with (
        patch("backend.observability.routers.command_center.require_admin"),
        patch(
            "backend.observability.routers.command_center.get_run_history",
            return_value=[],
        ),
    ):
        result = await get_pipeline_detail(days=7, user=_admin_user(), db=AsyncMock())

    assert result["total"] == 0
    assert result["runs"] == []
