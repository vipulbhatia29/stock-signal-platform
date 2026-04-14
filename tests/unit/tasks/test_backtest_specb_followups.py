"""Tests for Spec B follow-up tickets: KAN-439, KAN-440, KAN-441."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


class TestBacktestDegradedStatus:
    """KAN-439: Return status=degraded when some tickers fail."""

    @pytest.mark.asyncio
    async def test_returns_ok_when_all_succeed(self) -> None:
        """Status is 'ok' when zero tickers fail."""
        mock_engine = MagicMock()
        mock_metrics = MagicMock(
            num_windows=5,
            mape=0.05,
            mae=1.0,
            rmse=1.5,
            direction_accuracy=0.8,
            ci_containment=0.9,
        )
        mock_engine.run_walk_forward = AsyncMock(return_value=mock_metrics)

        mock_mv = MagicMock()
        mock_mv.id = uuid.uuid4()
        mock_mv.training_data_start = date(2024, 1, 1)
        mock_mv.training_data_end = date(2025, 12, 31)

        mock_mv_result = MagicMock()
        mock_mv_result.scalar_one_or_none.return_value = mock_mv

        mock_execute_result = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                # get_all_referenced_tickers query
                MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=["AAPL"])))
                ),
                # ModelVersion select
                mock_mv_result,
                # pg_insert execute
                mock_execute_result,
            ]
        )
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        from backend.tasks.forecasting import _run_backtest_async

        with (
            patch("backend.tasks.forecasting.settings") as mock_settings,
            patch("backend.tasks.forecasting.BacktestEngine", return_value=mock_engine),
            patch("backend.tasks.forecasting.async_session_factory", return_value=mock_factory),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL"],
            ),
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            mock_settings.BACKTEST_ENABLED = True
            result = await bypass_tracked(_run_backtest_async)(
                ticker="AAPL", horizon_days=90, run_id=uuid.uuid4()
            )

        assert result["status"] == "ok"
        assert result["completed"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_returns_degraded_when_some_fail(self) -> None:
        """Status is 'degraded' when at least one ticker fails."""
        mock_engine = MagicMock()
        mock_engine.run_walk_forward = AsyncMock(side_effect=RuntimeError("boom"))

        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        from backend.tasks.forecasting import _run_backtest_async

        with (
            patch("backend.tasks.forecasting.settings") as mock_settings,
            patch("backend.tasks.forecasting.BacktestEngine", return_value=mock_engine),
            patch("backend.tasks.forecasting.async_session_factory", return_value=mock_factory),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL"],
            ),
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            mock_settings.BACKTEST_ENABLED = True
            result = await bypass_tracked(_run_backtest_async)(
                ticker="AAPL", horizon_days=90, run_id=uuid.uuid4()
            )

        assert result["status"] == "degraded"
        assert result["failed"] == 1
        assert result["failed_tickers"] == ["AAPL"]

    @pytest.mark.asyncio
    async def test_failed_tickers_list_included(self) -> None:
        """Result includes failed_tickers list with actual ticker symbols."""
        mock_engine = MagicMock()
        mock_engine.run_walk_forward = AsyncMock(side_effect=RuntimeError("boom"))

        mock_session = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        from backend.tasks.forecasting import _run_backtest_async

        with (
            patch("backend.tasks.forecasting.settings") as mock_settings,
            patch("backend.tasks.forecasting.BacktestEngine", return_value=mock_engine),
            patch("backend.tasks.forecasting.async_session_factory", return_value=mock_factory),
            patch(
                "backend.tasks.forecasting.get_all_referenced_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", "MSFT"],
            ),
            patch("backend.tasks.forecasting.mark_stages_updated", new_callable=AsyncMock),
        ):
            mock_settings.BACKTEST_ENABLED = True
            result = await bypass_tracked(_run_backtest_async)(
                ticker=None, horizon_days=90, run_id=uuid.uuid4()
            )

        assert result["status"] == "degraded"
        assert result["failed"] == 2
        assert set(result["failed_tickers"]) == {"AAPL", "MSFT"}


class TestBacktestUpsert:
    """KAN-440: BacktestRun UniqueConstraint + upsert on re-run."""

    def test_unique_constraint_defined_on_model(self) -> None:
        """BacktestRun has a unique constraint on (ticker, mv, config, date, horizon)."""
        from backend.models.backtest import BacktestRun

        constraint_names = [
            c.name for c in BacktestRun.__table__.constraints if hasattr(c, "name") and c.name
        ]
        assert "uq_backtest_runs_ticker_mv_config_date_horizon" in constraint_names

    def test_unique_constraint_columns(self) -> None:
        """Constraint covers the correct 5 columns."""
        from sqlalchemy import UniqueConstraint as UC

        from backend.models.backtest import BacktestRun

        uq = next(
            c
            for c in BacktestRun.__table__.constraints
            if isinstance(c, UC) and c.name == "uq_backtest_runs_ticker_mv_config_date_horizon"
        )
        col_names = {col.name for col in uq.columns}
        assert col_names == {
            "ticker",
            "model_version_id",
            "config_label",
            "test_start",
            "horizon_days",
        }

    def test_migration_029_revision_chain(self) -> None:
        """Migration 029 chains from 028."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.029_backtest_unique_constraint")
        assert mod.down_revision == "a7b8c9d0e1f2"
        assert mod.revision == "b3c4d5e6f7a8"


class TestBacktestTimeLimit:
    """KAN-441: Celery time_limit on run_backtest_task."""

    def test_soft_time_limit_set(self) -> None:
        """run_backtest_task has a soft_time_limit of 3300s (55 min)."""
        from backend.tasks.forecasting import run_backtest_task

        assert run_backtest_task.soft_time_limit == 3300

    def test_hard_time_limit_set(self) -> None:
        """run_backtest_task has a hard time_limit of 3600s (60 min)."""
        from backend.tasks.forecasting import run_backtest_task

        assert run_backtest_task.time_limit == 3600

    def test_soft_limit_less_than_hard_limit(self) -> None:
        """Soft limit must be less than hard limit for graceful shutdown."""
        from backend.tasks.forecasting import run_backtest_task

        assert run_backtest_task.soft_time_limit < run_backtest_task.time_limit
