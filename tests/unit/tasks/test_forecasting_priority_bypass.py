"""Tests for Spec E.1 (forecast cap + priority) and E.2 (weekly retrain)."""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.forecasting import MAX_NEW_MODELS_PER_NIGHT
from tests.unit.tasks._tracked_helper_bypass import (
    bypass_tracked,  # noqa: F401 — used in sweep test
)


def test_max_new_models_per_night_is_100() -> None:
    """Spec E.1: nightly sweep cap raised from 20 to 100."""
    assert MAX_NEW_MODELS_PER_NIGHT == 100


def test_retrain_single_ticker_task_has_priority_param() -> None:
    """Spec E.1: retrain_single_ticker_task accepts a priority kwarg."""
    from backend.tasks.forecasting import retrain_single_ticker_task

    sig = inspect.signature(retrain_single_ticker_task)
    assert "priority" in sig.parameters
    assert sig.parameters["priority"].default is False


def test_ingest_ticker_dispatch_site_passes_priority_true() -> None:
    """Spec E.1: ingest_ticker dispatch site passes priority=True.

    Verify via source inspection that the retrain dispatch in pipelines.py
    uses priority=True — avoids brittle full-pipeline mock.
    """
    import inspect

    from backend.services import pipelines

    source = inspect.getsource(pipelines.ingest_ticker)
    assert "priority=True" in source, (
        "ingest_ticker must pass priority=True to retrain_single_ticker_task.delay"
    )


@pytest.mark.asyncio
async def test_nightly_sweep_respects_cap_at_100() -> None:
    """Spec E.1: nightly sweep dispatches at most 100 new-ticker training tasks."""
    from backend.tasks.forecasting import _forecast_refresh_async

    existing_mv = MagicMock()
    existing_mv.id = uuid.uuid4()
    existing_mv.ticker = "AAPL"
    existing_mv.is_active = True
    existing_mv.model_type = "prophet"

    # 120 new tickers — only 100 should be dispatched
    new_tickers = [f"TICK{i:03d}" for i in range(120)]
    all_tickers = ["AAPL"] + new_tickers

    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = [existing_mv]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_db_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "backend.tasks.forecasting.async_session_factory",
            return_value=mock_session_ctx,
        ),
        patch(
            "backend.tasks.forecasting._runner.record_ticker_success",
            new_callable=AsyncMock,
        ),
        patch("backend.tools.forecasting.predict_forecast", new=AsyncMock(return_value=[])),
        patch(
            "backend.services.ticker_universe.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=all_tickers,
        ),
        patch(
            "backend.tasks.forecasting._get_price_data_counts",
            new_callable=AsyncMock,
            return_value={t: 300 for t in new_tickers},
        ),
        patch("backend.tasks.forecasting.retrain_single_ticker_task") as mock_retrain_task,
    ):
        result = await bypass_tracked(_forecast_refresh_async)(run_id=uuid.uuid4())

    assert mock_retrain_task.delay.call_count == MAX_NEW_MODELS_PER_NIGHT
    assert result["refreshed"] == 1


# ── Spec E.2: Weekly retrain ──────────────────────────────────────────────────


def test_weekly_retrain_beat_schedule_present() -> None:
    """Spec E.2: model_retrain_all_task runs Sunday 02:00 ET weekly."""
    from celery.schedules import crontab

    from backend.tasks import celery_app

    assert "model-retrain-weekly" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["model-retrain-weekly"]
    assert entry["task"] == "backend.tasks.forecasting.model_retrain_all_task"
    schedule = entry["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule._orig_hour == 2
    assert schedule._orig_minute == 0
    assert schedule._orig_day_of_week == 0


def test_biweekly_beat_entry_removed() -> None:
    """Spec E.2: old 'model-retrain-biweekly' key must not exist."""
    from backend.tasks import celery_app

    assert "model-retrain-biweekly" not in celery_app.conf.beat_schedule


# ---------------------------------------------------------------------------
# Spec A gap: mark_stages_updated("forecast") in _forecast_refresh_async
# ---------------------------------------------------------------------------


def test_forecast_refresh_marks_forecast_stage() -> None:
    """_forecast_refresh_async calls mark_stages_updated('forecast') for refreshed tickers."""
    import inspect

    from backend.tasks import forecasting

    source = inspect.getsource(forecasting._forecast_refresh_async)
    assert 'mark_stages_updated(refreshed_tickers, "forecast")' in source, (
        "forecast refresh must call mark_stages_updated for 'forecast' stage"
    )


def test_forecast_refresh_tracks_refreshed_tickers() -> None:
    """_forecast_refresh_async collects refreshed tickers for stage marking."""
    import inspect

    from backend.tasks import forecasting

    source = inspect.getsource(forecasting._forecast_refresh_async)
    assert "refreshed_tickers" in source, "forecast refresh must track refreshed tickers in a list"


def test_registry_schedule_says_weekly() -> None:
    """Pipeline registry config describes retrain schedule as 'weekly', not 'biweekly'."""
    from backend.services.pipeline_registry_config import build_registry

    registry = build_registry()
    task = registry.get_task("backend.tasks.forecasting.model_retrain_all_task")
    assert task is not None
    assert "weekly" in task.schedule.lower()
    assert "biweekly" not in task.schedule.lower()
