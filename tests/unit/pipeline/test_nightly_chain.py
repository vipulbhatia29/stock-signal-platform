"""Unit tests for the nightly pipeline chain and recommendation generation task."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tasks.market_data import _nightly_price_refresh_async

# ---------------------------------------------------------------------------
# Nightly price refresh with PipelineRunner
# ---------------------------------------------------------------------------


class TestNightlyPriceRefresh:
    """Tests for _nightly_price_refresh_async with PipelineRunner tracking."""

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._get_all_watchlist_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._refresh_ticker_async", new_callable=AsyncMock)
    async def test_full_success(self, mock_refresh, mock_gap, mock_tickers, mock_runner) -> None:
        """Full nightly run with all tickers succeeding should return 'success'."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_gap.return_value = []
        mock_tickers.return_value = ["AAPL", "MSFT"]
        mock_runner.start_run = AsyncMock(return_value="run-id")
        mock_refresh.return_value = {"ticker": "X", "status": "ok"}
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.complete_run = AsyncMock(return_value="success")
        mock_runner.update_watermark = AsyncMock()

        result = await _nightly_price_refresh_async()

        assert result["status"] == "success"
        assert result["tickers_total"] == 2
        assert mock_runner.record_ticker_success.call_count == 2
        mock_runner.complete_run.assert_called_once()
        mock_runner.update_watermark.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._get_all_watchlist_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    @patch("backend.tasks.market_data._refresh_ticker_async", new_callable=AsyncMock)
    async def test_partial_failure(self, mock_refresh, mock_gap, mock_tickers, mock_runner) -> None:
        """Nightly run with some failures should return 'partial'."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_gap.return_value = []
        mock_tickers.return_value = ["AAPL", "TSLA"]
        mock_runner.start_run = AsyncMock(return_value="run-id")

        # AAPL succeeds, TSLA fails
        mock_refresh.side_effect = [
            {"ticker": "AAPL", "status": "ok"},
            Exception("yfinance timeout"),
        ]
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.record_ticker_failure = AsyncMock()
        mock_runner.complete_run = AsyncMock(return_value="partial")
        mock_runner.update_watermark = AsyncMock()

        result = await _nightly_price_refresh_async()

        assert result["status"] == "partial"
        mock_runner.record_ticker_success.assert_called_once()
        mock_runner.record_ticker_failure.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._get_all_watchlist_tickers", new_callable=AsyncMock)
    @patch("backend.tasks.market_data.detect_gap", new_callable=AsyncMock)
    async def test_no_tickers(self, mock_gap, mock_tickers, mock_runner) -> None:
        """Nightly run with no tickers should return early."""
        mock_runner.detect_stale_runs = AsyncMock(return_value=[])
        mock_gap.return_value = []
        mock_tickers.return_value = []

        result = await _nightly_price_refresh_async()

        assert result["status"] == "no_tickers"
        assert result["tickers_total"] == 0

    @pytest.mark.asyncio
    @patch("backend.tasks.market_data._runner")
    @patch("backend.tasks.market_data._get_all_watchlist_tickers", new_callable=AsyncMock)
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

        await _nightly_price_refresh_async()

        mock_set_status.assert_called_once_with("price_refresh", "backfilling")


# ---------------------------------------------------------------------------
# Nightly chain orchestrator
# ---------------------------------------------------------------------------


class TestNightlyPipelineChain:
    """Tests for the nightly_pipeline_chain_task."""

    @patch("backend.tasks.portfolio.snapshot_all_portfolios_task")
    @patch("backend.tasks.recommendations.generate_recommendations_task")
    @patch("backend.tasks.market_data.nightly_price_refresh_task")
    def test_chain_calls_all_steps(self, mock_price, mock_recs, mock_snapshot) -> None:
        """Chain should call price refresh, recommendations, and snapshot."""
        from backend.tasks.market_data import nightly_pipeline_chain_task

        mock_price.return_value = {"status": "success"}
        mock_recs.return_value = {"status": "success", "recommendations": 5}
        mock_snapshot.return_value = {"snapshots_created": 3}

        result = nightly_pipeline_chain_task()

        assert result["price_refresh"]["status"] == "success"
        assert result["recommendations"]["recommendations"] == 5
        assert result["portfolio_snapshots"]["snapshots_created"] == 3
        mock_price.assert_called_once()
        mock_recs.assert_called_once()
        mock_snapshot.assert_called_once()


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

        result = await _generate_recommendations_async()

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
