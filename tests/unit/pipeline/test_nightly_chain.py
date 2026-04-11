"""Unit tests for the nightly pipeline chain and recommendation generation task."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.market_data import _nightly_price_refresh_async
from tests.unit.tasks._tracked_helper_bypass import bypass_tracked

# ---------------------------------------------------------------------------
# Nightly price refresh with PipelineRunner
# ---------------------------------------------------------------------------


class TestNightlyPriceRefresh:
    """Tests for _nightly_price_refresh_async with PipelineRunner tracking."""

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._load_spy_closes", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._get_all_referenced_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._refresh_ticker_async", new_callable=AsyncMock)
    async def test_full_success(
        self,
        mock_refresh,
        mock_gap,
        mock_tickers,
        mock_spy,
        mock_runner,
    ) -> None:
        """Full nightly run with all tickers succeeding should return 'success'."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_spy.return_value = None
        mock_gap.return_value = []
        mock_tickers.return_value = ["AAPL", "MSFT"]
        mock_runner.start_run = AsyncMock(return_value="run-id")
        mock_refresh.return_value = {"ticker": "X", "status": "ok"}
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.complete_run = AsyncMock(return_value="success")
        mock_runner.update_watermark = AsyncMock()

        result = await bypass_tracked(_nightly_price_refresh_async)(run_id=uuid.uuid4())

        assert result["status"] == "success"
        assert result["tickers_total"] == 2
        assert mock_runner.record_ticker_success.call_count == 2
        mock_runner.complete_run.assert_called_once()
        mock_runner.update_watermark.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._load_spy_closes", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._get_all_referenced_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._refresh_ticker_async", new_callable=AsyncMock)
    async def test_partial_failure(
        self,
        mock_refresh,
        mock_gap,
        mock_tickers,
        mock_spy,
        mock_runner,
    ) -> None:
        """Nightly run with some failures should return 'partial'."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_gap.return_value = []
        mock_tickers.return_value = ["AAPL", "TSLA"]
        mock_spy.return_value = None  # SPY closes (not used in this test)
        mock_runner.start_run = AsyncMock(return_value="run-id")

        # SPY refresh first, then AAPL succeeds, TSLA fails
        mock_refresh.side_effect = [
            {"ticker": "SPY", "status": "ok"},  # explicit SPY refresh
            {"ticker": "AAPL", "status": "ok"},
            Exception("yfinance timeout"),
        ]
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.record_ticker_failure = AsyncMock()
        mock_runner.complete_run = AsyncMock(return_value="partial")
        mock_runner.update_watermark = AsyncMock()

        result = await bypass_tracked(_nightly_price_refresh_async)(run_id=uuid.uuid4())

        assert result["status"] == "partial"
        mock_runner.record_ticker_success.assert_called_once()
        mock_runner.record_ticker_failure.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._get_all_referenced_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    async def test_no_tickers(self, mock_gap, mock_tickers, mock_runner) -> None:
        """Nightly run with no tickers should return early."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_gap.return_value = []
        mock_tickers.return_value = []

        result = await bypass_tracked(_nightly_price_refresh_async)(run_id=uuid.uuid4())

        assert result["status"] == "no_tickers"
        assert result["tickers_total"] == 0

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._get_all_referenced_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.set_watermark_status", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._refresh_ticker_async", new_callable=AsyncMock)
    async def test_gap_detected_triggers_backfill_log(
        self, mock_refresh, mock_set_status, mock_gap, mock_tickers, mock_runner
    ) -> None:
        """Gap detection should set watermark to 'backfilling'."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_gap.return_value = [date(2026, 3, 19), date(2026, 3, 20)]
        mock_tickers.return_value = ["AAPL"]
        mock_runner.start_run = AsyncMock(return_value="run-id")
        mock_refresh.return_value = {"ticker": "AAPL", "status": "ok"}
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.complete_run = AsyncMock(return_value="success")
        mock_runner.update_watermark = AsyncMock()

        await bypass_tracked(_nightly_price_refresh_async)(run_id=uuid.uuid4())

        mock_set_status.assert_called_once_with("price_refresh", "backfilling")


# ---------------------------------------------------------------------------
# Nightly chain orchestrator
# ---------------------------------------------------------------------------


class TestNightlyPipelineChain:
    """Tests for the nightly_pipeline_chain_task."""

    @patch("backend.tasks.portfolio.snapshot_health_task")
    @patch("backend.tasks.alerts.generate_alerts_task")
    @patch("backend.tasks.evaluation.check_drift_task")
    @patch("backend.tasks.convergence.compute_convergence_snapshot_task")
    @patch("backend.tasks.evaluation.evaluate_recommendations_task")
    @patch("backend.tasks.evaluation.evaluate_forecasts_task")
    @patch("backend.tasks.portfolio.snapshot_all_portfolios_task")
    @patch("backend.tasks.recommendations.generate_recommendations_task")
    @patch("backend.tasks.forecasting.forecast_refresh_task")
    @patch("backend.tasks.market_data.nightly_price_refresh_task")
    def test_chain_calls_all_steps(
        self,
        mock_price,
        mock_forecast,
        mock_recs,
        mock_snapshot,
        mock_eval_fc,
        mock_eval_rec,
        mock_convergence,
        mock_drift,
        mock_alerts,
        mock_health_snapshot,
    ) -> None:
        """Chain should call all 10 pipeline steps in order (including convergence phase 3)."""
        from backend.tasks.market_data import nightly_pipeline_chain_task

        mock_price.return_value = {"status": "success"}
        mock_forecast.return_value = {"status": "success", "refreshed": 10}
        mock_recs.return_value = {"status": "success", "recommendations": 5}
        mock_eval_fc.return_value = {"status": "no_pending", "evaluated": 0}
        mock_eval_rec.return_value = {"status": "success", "evaluated": 0}
        mock_convergence.return_value = {"status": "ok", "computed": 50}
        mock_drift.return_value = {"degraded": [], "retrain_triggered": []}
        mock_alerts.return_value = {"alerts_created": 2}
        mock_snapshot.return_value = {"snapshots_created": 3}
        mock_health_snapshot.return_value = {"computed": 3, "skipped": 0}

        result = nightly_pipeline_chain_task()

        assert result["price_refresh"]["status"] == "success"
        assert result["forecast_refresh"]["refreshed"] == 10
        assert result["recommendations"]["recommendations"] == 5
        assert result["forecast_evaluation"]["status"] == "no_pending"
        assert result["recommendation_evaluation"]["evaluated"] == 0
        assert result["convergence"]["computed"] == 50
        assert result["drift"]["degraded"] == []
        assert result["alerts"]["alerts_created"] == 2
        assert result["portfolio_snapshots"]["snapshots_created"] == 3
        assert result["health_snapshots"]["computed"] == 3
        mock_price.assert_called_once()
        mock_forecast.assert_called_once()
        mock_recs.assert_called_once()
        mock_eval_fc.assert_called_once()
        mock_eval_rec.assert_called_once()
        mock_convergence.assert_called_once()
        mock_drift.assert_called_once()
        mock_alerts.assert_called_once()
        mock_snapshot.assert_called_once()
        mock_health_snapshot.assert_called_once()

    @patch("backend.tasks.portfolio.snapshot_health_task")
    @patch("backend.tasks.alerts.generate_alerts_task")
    @patch("backend.tasks.evaluation.check_drift_task")
    @patch("backend.tasks.convergence.compute_convergence_snapshot_task")
    @patch("backend.tasks.evaluation.evaluate_recommendations_task")
    @patch("backend.tasks.evaluation.evaluate_forecasts_task")
    @patch("backend.tasks.portfolio.snapshot_all_portfolios_task")
    @patch("backend.tasks.recommendations.generate_recommendations_task")
    @patch("backend.tasks.forecasting.forecast_refresh_task")
    @patch("backend.tasks.market_data.nightly_price_refresh_task")
    def test_phase_ordering_drift_after_forecast_eval(
        self,
        mock_price,
        mock_forecast,
        mock_recs,
        mock_snapshot,
        mock_eval_fc,
        mock_eval_rec,
        mock_convergence,
        mock_drift,
        mock_alerts,
        mock_health_snapshot,
    ) -> None:
        """Drift detection (phase 4) must run after convergence + forecast eval.

        Verifies convergence (phase 3) precedes drift (phase 4), and drift
        detection reads the MAPE values that forecast evaluation (phase 2) updates.
        """
        from backend.tasks.market_data import nightly_pipeline_chain_task

        call_order: list[str] = []

        def _track(name: str, return_value: dict):
            def _side_effect(*args, **kwargs):
                call_order.append(name)
                return return_value

            return _side_effect

        mock_price.side_effect = _track("price_refresh", {"status": "success"})
        mock_forecast.side_effect = _track("forecast_refresh", {"status": "ok"})
        mock_recs.side_effect = _track("recommendations", {"status": "ok"})
        mock_eval_fc.side_effect = _track("forecast_eval", {"status": "ok"})
        mock_eval_rec.side_effect = _track("rec_eval", {"status": "ok"})
        mock_convergence.side_effect = _track("convergence", {"status": "ok", "computed": 0})
        mock_drift.side_effect = _track("drift", {"degraded": []})
        mock_alerts.side_effect = _track("alerts", {"alerts_created": 0})
        mock_snapshot.side_effect = _track("portfolio_snapshots", {"snapshotted": 0})
        mock_health_snapshot.side_effect = _track("health_snapshots", {"computed": 0})

        nightly_pipeline_chain_task()

        # Price refresh must be first (phase 1)
        assert call_order[0] == "price_refresh"

        # Convergence must come after phase 2 (after forecast_eval)
        convergence_idx = call_order.index("convergence")
        fc_idx = call_order.index("forecast_eval")
        assert convergence_idx > fc_idx, (
            f"convergence ({convergence_idx}) should run after forecast_eval ({fc_idx})"
        )

        # Drift must come after convergence (phase 4 after phase 3)
        drift_idx = call_order.index("drift")
        assert drift_idx > convergence_idx, (
            f"drift ({drift_idx}) should run after convergence ({convergence_idx})"
        )

        # Alerts must come after drift (phase 5 after phase 4)
        alerts_idx = call_order.index("alerts")
        assert alerts_idx > drift_idx, f"alerts ({alerts_idx}) should run after drift ({drift_idx})"

    @patch("backend.tasks.portfolio.snapshot_health_task")
    @patch("backend.tasks.alerts.generate_alerts_task")
    @patch("backend.tasks.evaluation.check_drift_task")
    @patch("backend.tasks.convergence.compute_convergence_snapshot_task")
    @patch("backend.tasks.evaluation.evaluate_recommendations_task")
    @patch("backend.tasks.evaluation.evaluate_forecasts_task")
    @patch("backend.tasks.portfolio.snapshot_all_portfolios_task")
    @patch("backend.tasks.recommendations.generate_recommendations_task")
    @patch("backend.tasks.forecasting.forecast_refresh_task")
    @patch("backend.tasks.market_data.nightly_price_refresh_task")
    def test_step_failure_does_not_block_pipeline(
        self,
        mock_price,
        mock_forecast,
        mock_recs,
        mock_snapshot,
        mock_eval_fc,
        mock_eval_rec,
        mock_convergence,
        mock_drift,
        mock_alerts,
        mock_health_snapshot,
    ) -> None:
        """A failing step in phase 2 should not crash the entire pipeline.

        Other parallel steps and subsequent phases should still run.
        """
        from backend.tasks.market_data import nightly_pipeline_chain_task

        mock_price.return_value = {"status": "success"}
        mock_forecast.side_effect = Exception("Prophet model crash")
        mock_recs.return_value = {"status": "success", "recommendations": 5}
        mock_eval_fc.return_value = {"status": "ok"}
        mock_eval_rec.return_value = {"status": "ok"}
        mock_convergence.return_value = {"status": "ok", "computed": 50}
        mock_drift.return_value = {"degraded": []}
        mock_alerts.return_value = {"alerts_created": 0}
        mock_snapshot.return_value = {"snapshotted": 3}
        mock_health_snapshot.return_value = {"computed": 3}

        result = nightly_pipeline_chain_task()

        # Failed step should have error status
        assert result["forecast_refresh"]["status"] == "failed"
        # Other steps should still succeed
        assert result["recommendations"]["recommendations"] == 5
        assert result["convergence"]["computed"] == 50
        assert result["drift"]["degraded"] == []
        assert result["health_snapshots"]["computed"] == 3

    @patch("backend.tasks.portfolio.snapshot_health_task")
    @patch("backend.tasks.alerts.generate_alerts_task")
    @patch("backend.tasks.evaluation.check_drift_task")
    @patch("backend.tasks.convergence.compute_convergence_snapshot_task")
    @patch("backend.tasks.evaluation.evaluate_recommendations_task")
    @patch("backend.tasks.evaluation.evaluate_forecasts_task")
    @patch("backend.tasks.portfolio.snapshot_all_portfolios_task")
    @patch("backend.tasks.recommendations.generate_recommendations_task")
    @patch("backend.tasks.forecasting.forecast_refresh_task")
    @patch("backend.tasks.market_data.nightly_price_refresh_task")
    def test_alerts_receive_drift_context(
        self,
        mock_price,
        mock_forecast,
        mock_recs,
        mock_snapshot,
        mock_eval_fc,
        mock_eval_rec,
        mock_convergence,
        mock_drift,
        mock_alerts,
        mock_health_snapshot,
    ) -> None:
        """Alert generation should receive drift detection results as context."""
        from backend.tasks.market_data import nightly_pipeline_chain_task

        mock_price.return_value = {"status": "success"}
        mock_forecast.return_value = {"status": "ok"}
        mock_recs.return_value = {"status": "ok"}
        mock_eval_fc.return_value = {"status": "ok"}
        mock_eval_rec.return_value = {"status": "ok"}
        mock_convergence.return_value = {"status": "ok", "computed": 50}
        drift_result = {"degraded": ["TSLA"], "retrain_triggered": ["TSLA"]}
        mock_drift.return_value = drift_result
        mock_alerts.return_value = {"alerts_created": 1}
        mock_snapshot.return_value = {"snapshotted": 3}
        mock_health_snapshot.return_value = {"computed": 3}

        nightly_pipeline_chain_task()

        mock_alerts.assert_called_once_with(pipeline_context=drift_result)


# ---------------------------------------------------------------------------
# Recommendation generation
# ---------------------------------------------------------------------------


class TestGenerateRecommendationsAsync:
    """Tests for _generate_recommendations_async."""

    @pytest.mark.asyncio
    @patch("backend.tasks.recommendations.async_session_factory")
    async def test_no_users_returns_early(self, mock_factory) -> None:
        """If no users exist, should return immediately."""
        from backend.tasks.recommendations import _generate_recommendations_async

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_cm

        # Return empty user list
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await bypass_tracked(_generate_recommendations_async)(run_id=uuid.uuid4())

        assert result["status"] == "no_users"
        assert result["recommendations"] == 0


# ---------------------------------------------------------------------------
# Beat schedule configuration
# ---------------------------------------------------------------------------


class TestBeatSchedule:
    """Tests for Celery beat schedule configuration."""

    def test_timezone_is_eastern(self) -> None:
        """Celery should be configured with US/Eastern timezone."""
        from backend.tasks import celery_app

        assert celery_app.conf.timezone == "US/Eastern"

    def test_nightly_pipeline_in_schedule(self) -> None:
        """Beat schedule should include the nightly pipeline chain."""
        from backend.tasks import celery_app

        assert "nightly-pipeline" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["nightly-pipeline"]
        assert entry["task"] == "backend.tasks.market_data.nightly_pipeline_chain_task"

    def test_intraday_refresh_in_schedule(self) -> None:
        """Beat schedule should still include the intraday watchlist refresh."""
        from backend.tasks import celery_app

        assert "refresh-all-watchlist-tickers" in celery_app.conf.beat_schedule

    def test_portfolio_snapshot_in_schedule(self) -> None:
        """Beat schedule should include daily portfolio snapshots."""
        from backend.tasks import celery_app

        assert "snapshot-all-portfolios-daily" in celery_app.conf.beat_schedule
