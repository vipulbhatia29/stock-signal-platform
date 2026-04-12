"""Tests for Celery tasks in eager mode.

Verifies that all tasks can be called with valid inputs without raising,
that error handling works correctly for invalid inputs, and that
fire-and-forget import paths resolve correctly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# market_data tasks
# ---------------------------------------------------------------------------


class TestRefreshTickerTask:
    """Tests for refresh_ticker_task."""

    def test_refresh_ticker_task_success(self) -> None:
        """refresh_ticker_task delegates to _refresh_ticker_async via asyncio.run."""
        with patch("asyncio.run", return_value={"ticker": "AAPL", "status": "ok"}) as mock_run:
            from backend.tasks.market_data import refresh_ticker_task

            result = refresh_ticker_task.run("AAPL")
            mock_run.assert_called_once()
            assert result["ticker"] == "AAPL"
            assert result["status"] == "ok"

    def test_refresh_ticker_task_reraises_on_exception(self) -> None:
        """refresh_ticker_task re-raises exceptions (triggering Celery retry)."""
        with patch("asyncio.run", side_effect=RuntimeError("DB connection failed")):
            from backend.tasks.market_data import refresh_ticker_task

            with pytest.raises(RuntimeError, match="DB connection failed"):
                refresh_ticker_task.run("TSLA")

    def test_refresh_ticker_task_import_path_valid(self) -> None:
        """Verify the task is importable and has the correct name."""
        from backend.tasks.market_data import refresh_ticker_task

        assert refresh_ticker_task.name == "backend.tasks.market_data.refresh_ticker_task"


class TestIntradayRefreshAllTask:
    """Tests for intraday_refresh_all_task (renamed from refresh_all_watchlist_tickers_task)."""

    def test_intraday_refresh_all_dispatches_per_ticker(self) -> None:
        """Task fans out one refresh_ticker_task per referenced ticker."""
        with (
            patch("asyncio.run", return_value=["AAPL", "MSFT"]) as mock_run,
            patch("backend.tasks.market_data.refresh_ticker_task") as mock_task,
        ):
            from backend.tasks.market_data import intraday_refresh_all_task

            result = intraday_refresh_all_task.run()
            mock_run.assert_called_once()
            assert mock_task.delay.call_count == 2
            assert result["dispatched"] == 2

    def test_intraday_refresh_all_empty_universe(self) -> None:
        """Empty universe results in 0 dispatched tasks."""
        with (
            patch("asyncio.run", return_value=[]),
            patch("backend.tasks.market_data.refresh_ticker_task") as mock_task,
        ):
            from backend.tasks.market_data import intraday_refresh_all_task

            result = intraday_refresh_all_task.run()
            mock_task.delay.assert_not_called()
            assert result["dispatched"] == 0

    def test_intraday_refresh_all_task_registered_with_new_name(self) -> None:
        """Task is registered under the new canonical Celery name."""
        from backend.tasks.market_data import intraday_refresh_all_task

        expected = "backend.tasks.market_data.intraday_refresh_all_task"
        assert intraday_refresh_all_task.name == expected

    def test_legacy_alias_warns_and_delegates(self) -> None:
        """Deprecated alias emits DeprecationWarning and delegates to new task."""
        import warnings

        with (
            patch("asyncio.run", return_value=["AAPL"]),
            patch("backend.tasks.market_data.refresh_ticker_task"),
        ):
            from backend.tasks.market_data import refresh_all_watchlist_tickers_task

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = refresh_all_watchlist_tickers_task.run()
                assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
                assert result["dispatched"] == 1


# ---------------------------------------------------------------------------
# portfolio tasks
# ---------------------------------------------------------------------------


class TestSnapshotAllPortfoliosTask:
    """Tests for snapshot_all_portfolios_task."""

    def test_snapshot_all_portfolios_success(self) -> None:
        """snapshot_all_portfolios_task calls async helper and returns count."""
        with patch(
            "asyncio.run",
            return_value={"snapshotted": 5, "skipped": 2},
        ) as mock_run:
            from backend.tasks.portfolio import snapshot_all_portfolios_task

            result = snapshot_all_portfolios_task.run()
            mock_run.assert_called_once()
            assert result["snapshotted"] == 5
            assert result["skipped"] == 2

    def test_snapshot_all_portfolios_import_valid(self) -> None:
        """snapshot_all_portfolios_task must be importable."""
        from backend.tasks.portfolio import snapshot_all_portfolios_task

        assert callable(snapshot_all_portfolios_task.run)


class TestSnapshotHealthTask:
    """Tests for snapshot_health_task."""

    def test_snapshot_health_task_success(self) -> None:
        """snapshot_health_task calls async helper and returns metrics."""
        with patch(
            "asyncio.run",
            return_value={"computed": 3, "skipped": 0},
        ) as mock_run:
            from backend.tasks.portfolio import snapshot_health_task

            result = snapshot_health_task.run()
            mock_run.assert_called_once()
            assert result["computed"] == 3

    def test_snapshot_health_task_import_valid(self) -> None:
        """snapshot_health_task must be importable with correct task name."""
        from backend.tasks.portfolio import snapshot_health_task

        assert "snapshot_health_task" in snapshot_health_task.name


# ---------------------------------------------------------------------------
# audit tasks
# ---------------------------------------------------------------------------


class TestAuditTasks:
    """Tests for audit purge tasks."""

    def test_purge_login_attempts_task_callable(self) -> None:
        """purge_login_attempts_task must be importable and callable."""
        with patch("asyncio.run", return_value=None):
            from backend.tasks.audit import purge_login_attempts_task

            assert callable(purge_login_attempts_task.run)

    def test_purge_deleted_accounts_task_callable(self) -> None:
        """purge_deleted_accounts_task must be importable and callable."""
        with patch("asyncio.run", return_value=None):
            from backend.tasks.audit import purge_deleted_accounts_task

            assert callable(purge_deleted_accounts_task.run)

    def test_purge_login_attempts_task_import_path(self) -> None:
        """Verify task name matches registered path."""
        from backend.tasks.audit import purge_login_attempts_task

        assert purge_login_attempts_task.name == "backend.tasks.audit.purge_login_attempts_task"

    def test_purge_deleted_accounts_task_import_path(self) -> None:
        """Verify deleted accounts task name matches registered path."""
        from backend.tasks.audit import purge_deleted_accounts_task

        assert purge_deleted_accounts_task.name == "backend.tasks.audit.purge_deleted_accounts_task"


# ---------------------------------------------------------------------------
# warm_data tasks
# ---------------------------------------------------------------------------


class TestWarmDataTasks:
    """Tests for warm data synchronization tasks."""

    def test_sync_analyst_consensus_callable(self) -> None:
        """sync_analyst_consensus_task must be importable."""
        from backend.tasks.warm_data import sync_analyst_consensus_task

        assert callable(sync_analyst_consensus_task.run)

    def test_sync_fred_indicators_callable(self) -> None:
        """sync_fred_indicators_task must be importable."""
        from backend.tasks.warm_data import sync_fred_indicators_task

        assert callable(sync_fred_indicators_task.run)

    def test_sync_institutional_holders_callable(self) -> None:
        """sync_institutional_holders_task must be importable."""
        from backend.tasks.warm_data import sync_institutional_holders_task

        assert callable(sync_institutional_holders_task.run)


# ---------------------------------------------------------------------------
# alerts task
# ---------------------------------------------------------------------------


class TestGenerateAlertsTask:
    """Tests for generate_alerts_task."""

    def test_generate_alerts_task_callable(self) -> None:
        """generate_alerts_task must be importable and callable."""
        from backend.tasks.alerts import generate_alerts_task

        assert callable(generate_alerts_task.run)

    def test_generate_alerts_task_with_invalid_context(self) -> None:
        """generate_alerts_task with None pipeline_context should not raise import errors."""
        with patch("asyncio.run", return_value={"alerts_created": 0}):
            from backend.tasks.alerts import generate_alerts_task

            # The task should accept None context (all defaults)
            result = generate_alerts_task.run(pipeline_context=None)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Fire-and-forget import path validation
# ---------------------------------------------------------------------------


class TestFireAndForgetImportPaths:
    """Verify fire-and-forget code paths resolve imports correctly.

    Fire-and-forget try-except blocks can silently mask import errors.
    These tests ensure the imports used inside those blocks actually work.
    """

    def test_dividends_import_resolves(self) -> None:
        """Dividends module used in fire-and-forget block must be importable."""
        from backend.tools.dividends import fetch_dividends, store_dividends

        assert callable(fetch_dividends)
        assert callable(store_dividends)

    def test_yfinance_import_resolves(self) -> None:
        """yfinance used in fire-and-forget must be importable."""
        import yfinance as yf

        assert hasattr(yf, "Ticker")

    def test_celery_tasks_all_registered(self) -> None:
        """All tasks listed in include= must be importable."""
        # Import each module explicitly (no dynamic imports — avoids CWE-706)
        import backend.tasks.alerts
        import backend.tasks.audit
        import backend.tasks.evaluation
        import backend.tasks.forecasting
        import backend.tasks.market_data
        import backend.tasks.pipeline
        import backend.tasks.portfolio
        import backend.tasks.recommendations
        import backend.tasks.warm_data

        for mod in [
            backend.tasks.market_data,
            backend.tasks.portfolio,
            backend.tasks.warm_data,
            backend.tasks.recommendations,
            backend.tasks.forecasting,
            backend.tasks.evaluation,
            backend.tasks.alerts,
            backend.tasks.pipeline,
            backend.tasks.audit,
        ]:
            assert mod is not None
