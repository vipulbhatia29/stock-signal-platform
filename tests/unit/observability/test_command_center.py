"""Unit tests for the Command Center aggregate endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.routers.command_center import (
    _collect_zone,
    _get_api_traffic,
    _get_pipeline,
)
from backend.schemas.command_center import (
    ApiTrafficZone,
    CeleryHealth,
    CommandCenterMeta,
    CommandCenterResponse,
    DatabaseHealth,
    LangfuseHealth,
    LlmOperationsZone,
    McpHealth,
    PipelineLastRun,
    PipelineWatermarkStatus,
    PipelineZone,
    RedisHealth,
    SystemHealthZone,
    TierHealth,
    TokenBudgetStatus,
)

# ---------------------------------------------------------------------------
# _collect_zone tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_zone_timeout() -> None:
    """Zone collector returns (name, None) when the coro exceeds timeout."""

    async def slow_coro() -> str:
        await asyncio.sleep(5)
        return "should not reach"

    name, result = await _collect_zone("slow_zone", slow_coro(), timeout=0.05)
    assert name == "slow_zone"
    assert result is None


@pytest.mark.asyncio
async def test_collect_zone_exception() -> None:
    """Zone collector returns (name, None) when the coro raises."""

    async def failing_coro() -> str:
        msg = "boom"
        raise RuntimeError(msg)

    name, result = await _collect_zone("bad_zone", failing_coro(), timeout=1.0)
    assert name == "bad_zone"
    assert result is None


@pytest.mark.asyncio
async def test_collect_zone_success() -> None:
    """Zone collector returns (name, data) on success."""

    async def ok_coro() -> dict:
        return {"status": "ok"}

    name, result = await _collect_zone("good_zone", ok_coro(), timeout=1.0)
    assert name == "good_zone"
    assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# _get_api_traffic tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_api_traffic_no_collector() -> None:
    """Returns empty ApiTrafficZone when http_metrics is not on app.state."""
    request = MagicMock()
    request.app.state = MagicMock(spec=[])  # no http_metrics attribute

    result = await _get_api_traffic(request)
    assert isinstance(result, ApiTrafficZone)
    assert result.sample_count == 0
    assert result.rps_avg == 0


@pytest.mark.asyncio
async def test_get_api_traffic_with_collector() -> None:
    """Returns populated ApiTrafficZone from http_metrics stats."""
    mock_metrics = AsyncMock()
    mock_metrics.get_stats.return_value = {
        "window_seconds": 300,
        "sample_count": 50,
        "rps_avg": 1.5,
        "latency_p50_ms": 12.0,
        "latency_p95_ms": 45.0,
        "latency_p99_ms": 100.0,
        "error_rate_pct": 2.5,
        "total_requests_today": 500,
        "total_errors_today": 10,
        "top_endpoints": [("GET:/api/v1/health", 200)],
    }

    request = MagicMock()
    request.app.state.http_metrics = mock_metrics

    result = await _get_api_traffic(request)
    assert isinstance(result, ApiTrafficZone)
    assert result.sample_count == 50
    assert result.rps_avg == 1.5
    assert result.latency_p95_ms == 45.0
    assert len(result.top_endpoints) == 1
    assert result.top_endpoints[0]["endpoint"] == "GET:/api/v1/health"


# ---------------------------------------------------------------------------
# _get_pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("backend.observability.routers.command_center.get_next_run_time")
@patch("backend.observability.routers.command_center.get_watermarks")
@patch("backend.observability.routers.command_center.get_latest_run")
async def test_get_pipeline_returns_all_fields(
    mock_latest: AsyncMock,
    mock_watermarks: AsyncMock,
    mock_next_run: MagicMock,
) -> None:
    """Pipeline zone returns last_run, watermarks, and next_run_at."""
    mock_latest.return_value = {
        "id": "abc-123",
        "pipeline_name": "nightly",
        "status": "completed",
        "started_at": "2026-03-31T21:30:00+00:00",
        "completed_at": "2026-03-31T22:00:00+00:00",
        "duration_seconds": 1800.0,
        "tickers_total": 100,
        "tickers_succeeded": 95,
        "tickers_failed": 5,
        "trigger": "scheduled",
        "retry_count": 0,
    }
    mock_watermarks.return_value = [
        {
            "pipeline_name": "nightly",
            "last_completed_date": "2026-03-31",
            "last_completed_at": "2026-03-31T22:00:00+00:00",
            "status": "ok",
            "days_since_last": 0,
            "has_gap": False,
        },
    ]
    mock_next_run.return_value = "2026-04-01T21:30:00-04:00"

    db = AsyncMock()
    result = await _get_pipeline(db)

    assert isinstance(result, PipelineZone)
    assert result.last_run is not None
    assert result.last_run.status == "completed"
    assert result.last_run.tickers_total == 100
    assert result.last_run.tickers_succeeded == 95
    assert result.last_run.tickers_failed == 5
    assert result.last_run.total_duration_seconds == 1800.0
    assert len(result.watermarks) == 1
    assert result.watermarks[0].pipeline == "nightly"
    assert result.watermarks[0].status == "ok"
    assert result.next_run_at == "2026-04-01T21:30:00-04:00"


@pytest.mark.asyncio
@patch("backend.observability.routers.command_center.get_next_run_time")
@patch("backend.observability.routers.command_center.get_watermarks")
@patch("backend.observability.routers.command_center.get_latest_run")
async def test_get_pipeline_no_runs(
    mock_latest: AsyncMock,
    mock_watermarks: AsyncMock,
    mock_next_run: MagicMock,
) -> None:
    """Pipeline zone handles no prior runs gracefully."""
    mock_latest.return_value = None
    mock_watermarks.return_value = []
    mock_next_run.return_value = "2026-04-01T21:30:00-04:00"

    db = AsyncMock()
    result = await _get_pipeline(db)

    assert isinstance(result, PipelineZone)
    assert result.last_run is None
    assert result.watermarks == []
    assert result.next_run_at is not None


# ---------------------------------------------------------------------------
# Schema instantiation tests
# ---------------------------------------------------------------------------


def test_command_center_response_full() -> None:
    """CommandCenterResponse instantiates with all 4 zones populated."""
    response = CommandCenterResponse(
        timestamp="2026-03-31T12:00:00Z",
        meta=CommandCenterMeta(assembly_ms=42, degraded_zones=[]),
        system_health=SystemHealthZone(
            status="ok",
            database=DatabaseHealth(
                healthy=True,
                latency_ms=1.5,
                pool_active=2,
                pool_size=5,
                pool_overflow=0,
            ),
            redis=RedisHealth(healthy=True, latency_ms=0.5),
            mcp=McpHealth(healthy=True, mode="stdio", tool_count=24, restarts=0),
            celery=CeleryHealth(workers=1, queued=0, beat_active=True),
            langfuse=LangfuseHealth(connected=True, traces_today=10, spans_today=50),
        ),
        api_traffic=ApiTrafficZone(
            sample_count=100,
            rps_avg=2.5,
            latency_p50_ms=10.0,
            latency_p95_ms=50.0,
        ),
        llm_operations=LlmOperationsZone(
            tiers=[
                TierHealth(model="llama-3.3-70b", status="healthy", failures_5m=0),
            ],
            cost_today_usd=0.05,
            cascade_rate_pct=5.0,
            token_budgets=[
                TokenBudgetStatus(model="llama-3.3-70b", tpm_used_pct=30.0),
            ],
        ),
        pipeline=PipelineZone(
            last_run=PipelineLastRun(
                started_at="2026-03-31T21:30:00Z",
                status="completed",
                tickers_total=100,
            ),
            watermarks=[
                PipelineWatermarkStatus(
                    pipeline="nightly",
                    last_date="2026-03-31",
                    status="ok",
                ),
            ],
            next_run_at="2026-04-01T21:30:00-04:00",
        ),
    )

    assert response.timestamp == "2026-03-31T12:00:00Z"
    assert response.meta.assembly_ms == 42
    assert response.system_health is not None
    assert response.api_traffic is not None
    assert response.llm_operations is not None
    assert response.pipeline is not None


def test_command_center_response_degraded_zones() -> None:
    """CommandCenterResponse accepts None zones and records degraded_zones."""
    response = CommandCenterResponse(
        timestamp="2026-03-31T12:00:00Z",
        meta=CommandCenterMeta(
            assembly_ms=100,
            degraded_zones=["system_health", "llm_operations"],
        ),
        system_health=None,
        api_traffic=ApiTrafficZone(),
        llm_operations=None,
        pipeline=None,
    )

    assert response.system_health is None
    assert response.llm_operations is None
    assert len(response.meta.degraded_zones) == 2
    assert "system_health" in response.meta.degraded_zones


def test_command_center_response_defaults() -> None:
    """CommandCenterResponse works with minimal required fields."""
    response = CommandCenterResponse(timestamp="2026-03-31T12:00:00Z")
    assert response.meta.assembly_ms == 0
    assert response.meta.degraded_zones == []
    assert response.system_health is None
    assert response.api_traffic is None
    assert response.llm_operations is None
    assert response.pipeline is None
