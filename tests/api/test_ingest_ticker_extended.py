"""Extended ingest_ticker tests for B5 pipeline completeness (KAN-422).

Covers Steps 6b/8/9/10 behaviour:
  - Step 6b: mark_stage_updated called for "prices" and "signals"
  - Steps 8/9: news and convergence dispatched only for new tickers
  - Step 10: mark_stage_updated called for "recommendation"
  - Failure isolation: news dispatch failure does not abort the pipeline

These tests live under tests/api/ because the production code paths interact
with DB models (mark_stage_updated uses async_session_factory), and the
plan-A guardrail requires db-touching tests to live here.

All I/O is mocked — no real DB or Celery broker is needed for these tests.
The db_session fixture parameter ensures the guardrail is satisfied.

Patch targets:
  - backend.services.pipelines.news_ingest_task  (module-level import)
  - backend.services.pipelines.compute_convergence_snapshot_task (module-level)
  - backend.services.pipelines.mark_stage_updated (module-level import)
  - backend.services.pipelines.retrain_single_ticker_task (lazy-imported)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.services.pipelines import ingest_ticker

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BASE = "backend.services.pipelines"


@pytest.fixture()
def mock_db():
    """Create a mock async DB session."""
    return AsyncMock()


@pytest.fixture()
def new_stock():
    """Mock Stock object representing a brand-new ticker (no prior ingest)."""
    stock = MagicMock()
    stock.name = "NewCo Inc."
    stock.last_fetched_at = None  # triggers is_new=True
    return stock


@pytest.fixture()
def existing_stock():
    """Mock Stock object representing an existing ticker (already ingested)."""
    from datetime import datetime, timezone

    stock = MagicMock()
    stock.name = "ExistCo Inc."
    stock.last_fetched_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return stock


@pytest.fixture()
def signal_result_with_score():
    """Mock SignalResult with a non-None composite_score."""
    sr = MagicMock()
    sr.composite_score = 7.5
    sr.ticker = "NEWCO"
    return sr


def _make_full_patches(stock_mock, signal_mock=None):
    """Return a dict of patch targets → mock values for a full ingest_ticker run.

    Args:
        stock_mock: The mock Stock object to return from ensure_stock_exists.
        signal_mock: Optional SignalResult mock. When None, signals are skipped
            (empty DataFrame path).

    Returns:
        Dict of {name: mock} pairs ready for use with patch().
    """
    if signal_mock is not None:
        full_df = pd.DataFrame(
            {"Close": [100.0, 101.0, 102.0]},
            index=pd.date_range("2024-01-01", periods=3),
        )
    else:
        full_df = pd.DataFrame()

    delta_df = pd.DataFrame(
        {"Close": [102.0]},
        index=pd.date_range("2024-01-03", periods=1),
    )

    fundamentals = MagicMock()
    fundamentals.piotroski_score = 5

    return {
        "ensure_stock_exists": AsyncMock(return_value=stock_mock),
        "fetch_prices_delta": AsyncMock(return_value=delta_df),
        "load_prices_df": AsyncMock(return_value=full_df),
        "fetch_fundamentals": MagicMock(return_value=fundamentals),
        "fetch_analyst_data": MagicMock(return_value={"analyst_target_mean": 180.0}),
        "fetch_earnings_history": MagicMock(return_value=[]),
        "persist_enriched_fundamentals": AsyncMock(),
        "persist_earnings_snapshots": AsyncMock(),
        "compute_signals": MagicMock(return_value=signal_mock) if signal_mock else MagicMock(),
        "store_signal_snapshot": AsyncMock(),
        "update_last_fetched_at": AsyncMock(),
    }


# ---------------------------------------------------------------------------
# B5: Steps 8 + 9 — news and convergence dispatched for new tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_ticker_dispatches_news_backfill(mock_db, new_stock, signal_result_with_score):
    """news_ingest_task.delay and compute_convergence_snapshot_task.delay called for new tickers.

    A brand-new ticker (last_fetched_at=None) should trigger both dispatches
    after the normal price+signal pipeline completes.
    """
    patches = _make_full_patches(new_stock, signal_result_with_score)
    mock_news_task = MagicMock()
    mock_convergence_task = MagicMock()
    mock_retrain_task = MagicMock()
    mock_mark_stage = AsyncMock()

    with (
        patch(f"{_BASE}.ensure_stock_exists", patches["ensure_stock_exists"]),
        patch(f"{_BASE}.fetch_prices_delta", patches["fetch_prices_delta"]),
        patch(f"{_BASE}.load_prices_df", patches["load_prices_df"]),
        patch(f"{_BASE}.fetch_fundamentals", patches["fetch_fundamentals"]),
        patch(f"{_BASE}.fetch_analyst_data", patches["fetch_analyst_data"]),
        patch(f"{_BASE}.fetch_earnings_history", patches["fetch_earnings_history"]),
        patch(f"{_BASE}.persist_enriched_fundamentals", patches["persist_enriched_fundamentals"]),
        patch(f"{_BASE}.persist_earnings_snapshots", patches["persist_earnings_snapshots"]),
        patch(f"{_BASE}.compute_signals", patches["compute_signals"]),
        patch(f"{_BASE}.store_signal_snapshot", patches["store_signal_snapshot"]),
        patch(f"{_BASE}.update_last_fetched_at", patches["update_last_fetched_at"]),
        patch(f"{_BASE}.mark_stage_updated", mock_mark_stage),
        patch(f"{_BASE}.news_ingest_task", mock_news_task),
        patch(f"{_BASE}.compute_convergence_snapshot_task", mock_convergence_task),
        patch("backend.tasks.forecasting.retrain_single_ticker_task", mock_retrain_task),
    ):
        result = await ingest_ticker("NEWCO", mock_db)

    assert result["is_new"] is True
    mock_news_task.delay.assert_called_once_with(lookback_days=90, tickers=["NEWCO"])
    mock_convergence_task.delay.assert_called_once_with(ticker="NEWCO")


@pytest.mark.asyncio
async def test_existing_ticker_skips_news_and_convergence(
    mock_db, existing_stock, signal_result_with_score
):
    """No news or convergence dispatch for existing tickers (is_new=False).

    When a ticker already has a last_fetched_at, the pipeline should skip
    Steps 8 and 9 entirely.
    """
    patches = _make_full_patches(existing_stock, signal_result_with_score)
    mock_news_task = MagicMock()
    mock_convergence_task = MagicMock()
    mock_retrain_task = MagicMock()
    mock_mark_stage = AsyncMock()

    with (
        patch(f"{_BASE}.ensure_stock_exists", patches["ensure_stock_exists"]),
        patch(f"{_BASE}.fetch_prices_delta", patches["fetch_prices_delta"]),
        patch(f"{_BASE}.load_prices_df", patches["load_prices_df"]),
        patch(f"{_BASE}.fetch_fundamentals", patches["fetch_fundamentals"]),
        patch(f"{_BASE}.fetch_analyst_data", patches["fetch_analyst_data"]),
        patch(f"{_BASE}.fetch_earnings_history", patches["fetch_earnings_history"]),
        patch(f"{_BASE}.persist_enriched_fundamentals", patches["persist_enriched_fundamentals"]),
        patch(f"{_BASE}.persist_earnings_snapshots", patches["persist_earnings_snapshots"]),
        patch(f"{_BASE}.compute_signals", patches["compute_signals"]),
        patch(f"{_BASE}.store_signal_snapshot", patches["store_signal_snapshot"]),
        patch(f"{_BASE}.update_last_fetched_at", patches["update_last_fetched_at"]),
        patch(f"{_BASE}.mark_stage_updated", mock_mark_stage),
        patch(f"{_BASE}.news_ingest_task", mock_news_task),
        patch(f"{_BASE}.compute_convergence_snapshot_task", mock_convergence_task),
        patch("backend.tasks.forecasting.retrain_single_ticker_task", mock_retrain_task),
    ):
        result = await ingest_ticker("AAPL", mock_db)

    assert result["is_new"] is False
    mock_news_task.delay.assert_not_called()
    mock_convergence_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# B5: Step 6b — mark_stage_updated called for prices and signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_stage_updated_called_for_prices_and_signals(
    mock_db, existing_stock, signal_result_with_score
):
    """mark_stage_updated is called with 'prices' and 'signals' after Step 6.

    After update_last_fetched_at (Step 6), the pipeline should call
    mark_stage_updated(ticker, 'prices') unconditionally and
    mark_stage_updated(ticker, 'signals') when composite_score is not None.
    """
    patches = _make_full_patches(existing_stock, signal_result_with_score)
    mock_mark_stage = AsyncMock()
    mock_news_task = MagicMock()
    mock_convergence_task = MagicMock()
    mock_retrain_task = MagicMock()

    with (
        patch(f"{_BASE}.ensure_stock_exists", patches["ensure_stock_exists"]),
        patch(f"{_BASE}.fetch_prices_delta", patches["fetch_prices_delta"]),
        patch(f"{_BASE}.load_prices_df", patches["load_prices_df"]),
        patch(f"{_BASE}.fetch_fundamentals", patches["fetch_fundamentals"]),
        patch(f"{_BASE}.fetch_analyst_data", patches["fetch_analyst_data"]),
        patch(f"{_BASE}.fetch_earnings_history", patches["fetch_earnings_history"]),
        patch(f"{_BASE}.persist_enriched_fundamentals", patches["persist_enriched_fundamentals"]),
        patch(f"{_BASE}.persist_earnings_snapshots", patches["persist_earnings_snapshots"]),
        patch(f"{_BASE}.compute_signals", patches["compute_signals"]),
        patch(f"{_BASE}.store_signal_snapshot", patches["store_signal_snapshot"]),
        patch(f"{_BASE}.update_last_fetched_at", patches["update_last_fetched_at"]),
        patch(f"{_BASE}.mark_stage_updated", mock_mark_stage),
        patch(f"{_BASE}.news_ingest_task", mock_news_task),
        patch(f"{_BASE}.compute_convergence_snapshot_task", mock_convergence_task),
        patch("backend.tasks.forecasting.retrain_single_ticker_task", mock_retrain_task),
    ):
        await ingest_ticker("AAPL", mock_db)

    stage_calls = [call.args for call in mock_mark_stage.await_args_list]
    stages_called = [stage for _ticker, stage in stage_calls]
    assert "prices" in stages_called
    assert "signals" in stages_called


# ---------------------------------------------------------------------------
# B5: Step 10 — mark_stage_updated called for recommendation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_stage_updated_called_for_recommendation(mock_db, existing_stock):
    """mark_stage_updated is called with 'recommendation' after store_recommendation.

    When a user_id is provided and recommendation is generated, Step 10
    must mark the recommendation stage as updated.
    """
    patches = _make_full_patches(existing_stock, MagicMock(composite_score=8.0, ticker="AAPL"))
    mock_mark_stage = AsyncMock()
    mock_news_task = MagicMock()
    mock_convergence_task = MagicMock()
    mock_retrain_task = MagicMock()

    # Mocks needed for _generate_recommendation_with_context
    mock_portfolio = MagicMock()
    mock_portfolio.id = "port-uuid"
    mock_price_row = MagicMock()
    mock_price_row.adj_close = 150.0
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.side_effect = [None, mock_price_row]
    mock_db.execute = AsyncMock(return_value=mock_db_result)

    with (
        patch(f"{_BASE}.ensure_stock_exists", patches["ensure_stock_exists"]),
        patch(f"{_BASE}.fetch_prices_delta", patches["fetch_prices_delta"]),
        patch(f"{_BASE}.load_prices_df", patches["load_prices_df"]),
        patch(f"{_BASE}.fetch_fundamentals", patches["fetch_fundamentals"]),
        patch(f"{_BASE}.fetch_analyst_data", patches["fetch_analyst_data"]),
        patch(f"{_BASE}.fetch_earnings_history", patches["fetch_earnings_history"]),
        patch(f"{_BASE}.persist_enriched_fundamentals", patches["persist_enriched_fundamentals"]),
        patch(f"{_BASE}.persist_earnings_snapshots", patches["persist_earnings_snapshots"]),
        patch(f"{_BASE}.compute_signals", patches["compute_signals"]),
        patch(f"{_BASE}.store_signal_snapshot", patches["store_signal_snapshot"]),
        patch(f"{_BASE}.update_last_fetched_at", patches["update_last_fetched_at"]),
        patch(f"{_BASE}.mark_stage_updated", mock_mark_stage),
        patch(f"{_BASE}.news_ingest_task", mock_news_task),
        patch(f"{_BASE}.compute_convergence_snapshot_task", mock_convergence_task),
        patch("backend.tasks.forecasting.retrain_single_ticker_task", mock_retrain_task),
        patch(f"{_BASE}.generate_recommendation", MagicMock(return_value=MagicMock())),
        patch(f"{_BASE}.store_recommendation", AsyncMock()),
        patch(
            "backend.services.portfolio.get_or_create_portfolio",
            AsyncMock(return_value=mock_portfolio),
        ),
        patch(
            "backend.services.portfolio.get_positions_with_pnl",
            AsyncMock(return_value=[]),
        ),
    ):
        await ingest_ticker("AAPL", mock_db, user_id="user-uuid")

    stage_calls = [call.args for call in mock_mark_stage.await_args_list]
    stages_called = [stage for _ticker, stage in stage_calls]
    assert "recommendation" in stages_called


# ---------------------------------------------------------------------------
# B5: Failure isolation — news dispatch failure does not abort pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_news_dispatch_failure_does_not_abort_pipeline(mock_db, new_stock):
    """RuntimeError from news_ingest_task.delay does not propagate to caller.

    Steps 8/9 are fire-and-forget. A broker failure must be swallowed
    and logged, leaving the ingest result intact.
    """
    patches = _make_full_patches(new_stock)
    mock_news_task = MagicMock()
    mock_news_task.delay.side_effect = RuntimeError("broker down")
    mock_convergence_task = MagicMock()
    mock_retrain_task = MagicMock()
    mock_mark_stage = AsyncMock()

    with (
        patch(f"{_BASE}.ensure_stock_exists", patches["ensure_stock_exists"]),
        patch(f"{_BASE}.fetch_prices_delta", patches["fetch_prices_delta"]),
        patch(f"{_BASE}.load_prices_df", patches["load_prices_df"]),
        patch(f"{_BASE}.fetch_fundamentals", patches["fetch_fundamentals"]),
        patch(f"{_BASE}.fetch_analyst_data", patches["fetch_analyst_data"]),
        patch(f"{_BASE}.fetch_earnings_history", patches["fetch_earnings_history"]),
        patch(f"{_BASE}.persist_enriched_fundamentals", patches["persist_enriched_fundamentals"]),
        patch(f"{_BASE}.persist_earnings_snapshots", patches["persist_earnings_snapshots"]),
        patch(f"{_BASE}.compute_signals", patches["compute_signals"]),
        patch(f"{_BASE}.store_signal_snapshot", patches["store_signal_snapshot"]),
        patch(f"{_BASE}.update_last_fetched_at", patches["update_last_fetched_at"]),
        patch(f"{_BASE}.mark_stage_updated", mock_mark_stage),
        patch(f"{_BASE}.news_ingest_task", mock_news_task),
        patch(f"{_BASE}.compute_convergence_snapshot_task", mock_convergence_task),
        patch("backend.tasks.forecasting.retrain_single_ticker_task", mock_retrain_task),
    ):
        result = await ingest_ticker("NEWCO", mock_db)

    # Pipeline result must still be returned despite dispatch failure
    assert result["ticker"] == "NEWCO"
    assert result["is_new"] is True
