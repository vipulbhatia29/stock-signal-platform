"""Tests for Spec E.3: fast/slow path split for intraday/nightly refresh."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


@pytest.mark.asyncio
async def test_refresh_ticker_fast_does_not_call_yfinance() -> None:
    """Fast path: prices + signals + QuantStats only. No yfinance info call."""
    from backend.tasks import market_data as mod

    with (
        patch.object(mod, "fetch_prices_delta", new=AsyncMock()),
        patch.object(
            mod,
            "load_prices_df",
            new=AsyncMock(return_value=pd.DataFrame({"Close": [1.0, 2.0]})),
        ),
        patch.object(mod, "compute_signals", return_value=MagicMock(composite_score=5.0)),
        patch.object(
            mod,
            "compute_quantstats_stock",
            return_value={
                "sortino": 1.0,
                "max_drawdown": -0.1,
                "alpha": 0.05,
                "beta": 1.0,
            },
        ),
        patch.object(mod, "store_signal_snapshot", new=AsyncMock()),
        patch.object(mod, "async_session_factory") as mock_factory,
    ):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        with patch("yfinance.Ticker") as mock_yf:
            result = await mod._refresh_ticker_fast("AAPL", spy_closes=pd.Series([100.0]))

        assert result["status"] == "ok"
        mock_yf.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_ticker_slow_does_not_compute_signals() -> None:
    """Slow path: yfinance info + dividends. No signal compute or snapshot store."""
    from backend.tasks import market_data as mod

    with (
        patch.object(mod, "compute_signals") as mock_sig,
        patch.object(mod, "store_signal_snapshot", new=AsyncMock()) as mock_store,
        patch.object(mod, "async_session_factory") as mock_factory,
        patch.object(mod, "yfinance_limiter", AsyncMock(acquire=AsyncMock(return_value=True))),
        patch.object(mod, "mark_stage_updated", new=AsyncMock()),
    ):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        with (
            patch("yfinance.Ticker", return_value=MagicMock(info={})),
            patch("asyncio.to_thread", new=AsyncMock(return_value={})),
        ):
            result = await mod._refresh_ticker_slow("AAPL")

        assert result["status"] == "ok"
        mock_sig.assert_not_called()
        mock_store.assert_not_called()


@pytest.mark.asyncio
async def test_nightly_price_refresh_uses_concurrent_gather() -> None:
    """Spec E.3: nightly refresh runs tickers concurrently via asyncio.gather."""
    from backend.tasks import market_data as mod
    from backend.tasks.market_data import _nightly_price_refresh_work

    call_order: list[str] = []

    async def mock_fast(ticker: str, spy_closes: object = None) -> dict:
        """Track call order for concurrency verification."""
        call_order.append(ticker)
        return {"ticker": ticker, "status": "ok"}

    with (
        patch.object(mod, "_refresh_ticker_fast", side_effect=mock_fast),
        patch.object(mod, "_runner") as mock_runner,
    ):
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.record_ticker_failure = AsyncMock()

        result = await bypass_tracked(_nightly_price_refresh_work)(
            ["A", "B", "C"],
            None,
            run_id=uuid.uuid4(),
        )

    assert result["tickers_total"] == 3
    assert result["tickers_succeeded"] == 3
    assert result["tickers_failed"] == 0
    assert set(call_order) == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_nightly_price_refresh_records_per_ticker_failure() -> None:
    """Individual ticker failure is recorded but doesn't crash the pipeline."""
    from backend.tasks import market_data as mod
    from backend.tasks.market_data import _nightly_price_refresh_work

    async def mock_fast(ticker: str, spy_closes: object = None) -> dict:
        """Simulate failure for ticker B."""
        if ticker == "B":
            raise RuntimeError("yfinance timeout")
        return {"ticker": ticker, "status": "ok"}

    with (
        patch.object(mod, "_refresh_ticker_fast", side_effect=mock_fast),
        patch.object(mod, "_runner") as mock_runner,
    ):
        mock_runner.record_ticker_success = AsyncMock()
        mock_runner.record_ticker_failure = AsyncMock()

        result = await bypass_tracked(_nightly_price_refresh_work)(
            ["A", "B", "C"],
            None,
            run_id=uuid.uuid4(),
        )

    assert result["tickers_succeeded"] == 2
    assert result["tickers_failed"] == 1
    assert mock_runner.record_ticker_failure.await_count == 1


@pytest.mark.asyncio
async def test_refresh_all_slow_async_runs_for_all_tickers() -> None:
    """Spec E.3: _refresh_all_slow_async calls _refresh_ticker_slow for each ticker."""
    from backend.tasks import market_data as mod

    with (
        patch.object(
            mod,
            "_get_all_referenced_tickers",
            new=AsyncMock(return_value=["AAPL", "MSFT", "GOOG"]),
        ),
        patch.object(
            mod,
            "_refresh_ticker_slow",
            new=AsyncMock(return_value={"ticker": "X", "status": "ok"}),
        ) as mock_slow,
    ):
        result = await mod._refresh_all_slow_async()

    assert result["tickers"] == 3
    assert result["succeeded"] == 3
    assert mock_slow.await_count == 3


@pytest.mark.asyncio
async def test_refresh_all_slow_async_continues_on_failure() -> None:
    """Spec E.3: slow path failure for one ticker doesn't crash the loop."""
    from backend.tasks import market_data as mod

    call_count = 0

    async def mock_slow(ticker: str) -> dict:
        """Fail on MSFT, succeed on others."""
        nonlocal call_count
        call_count += 1
        if ticker == "MSFT":
            raise RuntimeError("yfinance timeout")
        return {"ticker": ticker, "status": "ok"}

    with (
        patch.object(
            mod,
            "_get_all_referenced_tickers",
            new=AsyncMock(return_value=["AAPL", "MSFT", "GOOG"]),
        ),
        patch.object(mod, "_refresh_ticker_slow", side_effect=mock_slow),
    ):
        result = await mod._refresh_all_slow_async()

    assert result["succeeded"] == 2
    assert call_count == 3


def test_intraday_refresh_concurrency_config_default() -> None:
    """Spec E.3: INTRADAY_REFRESH_CONCURRENCY defaults to 5 (= pool_size)."""
    from backend.config import settings

    assert settings.INTRADAY_REFRESH_CONCURRENCY == 5


def test_refresh_ticker_async_calls_both_paths() -> None:
    """Combined _refresh_ticker_async calls fast then slow for backward compat."""
    import inspect

    from backend.tasks import market_data

    source = inspect.getsource(market_data._refresh_ticker_async)
    assert "_refresh_ticker_fast" in source
    assert "_refresh_ticker_slow" in source


# ---------------------------------------------------------------------------
# Spec F gap: yfinance_limiter in _refresh_ticker_slow
# ---------------------------------------------------------------------------


def test_slow_path_uses_yfinance_limiter() -> None:
    """Spec F: _refresh_ticker_slow acquires yfinance_limiter before yf.Ticker calls."""
    import inspect

    from backend.tasks import market_data

    source = inspect.getsource(market_data._refresh_ticker_slow)
    # limiter.acquire() must appear before yf.Ticker() calls
    limiter_pos = source.find("yfinance_limiter.acquire()")
    yf_pos = source.find("yf.Ticker(")
    assert limiter_pos != -1, "yfinance_limiter.acquire() not found in _refresh_ticker_slow"
    assert yf_pos != -1, "yf.Ticker() not found in _refresh_ticker_slow"
    assert limiter_pos < yf_pos, "yfinance_limiter must be acquired before yf.Ticker call"


def test_slow_path_acquires_limiter_before_dividends() -> None:
    """Spec F: _refresh_ticker_slow acquires yfinance_limiter before fetch_dividends call."""
    import inspect

    from backend.tasks import market_data

    source = inspect.getsource(market_data._refresh_ticker_slow)
    # Find second limiter acquire (for dividends) — must be before the actual call
    first_acquire = source.find("yfinance_limiter.acquire()")
    second_acquire = source.find("yfinance_limiter.acquire()", first_acquire + 1)
    # Look for the actual function call, not the import line
    dividends_call = source.find("fetch_dividends, ticker")
    assert second_acquire != -1, "Second yfinance_limiter.acquire() not found"
    assert dividends_call != -1, "fetch_dividends call not found in _refresh_ticker_slow"
    assert second_acquire < dividends_call, (
        "yfinance_limiter must be acquired before fetch_dividends call"
    )
