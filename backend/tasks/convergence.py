"""Celery task for computing daily signal convergence snapshots.

Backfill helpers
----------------
_backfill_actual_returns   — fills actual_return_90d / actual_return_180d for past rows
_bulk_latest_price         — DISTINCT ON price fetch up to a ceiling date (7-day window)
_bulk_price_on_date        — thin wrapper for fetching price at a specific historical date

Circular-import note
--------------------
backend.services.signal_convergence imports classification helpers (_classify_*)
from this module, so SignalConvergenceService is imported lazily inside the
async implementation to avoid a circular import at module load time.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.convergence import SignalConvergenceDaily
from backend.models.price import StockPrice
from backend.services.ticker_state import mark_stage_updated
from backend.services.ticker_universe import get_all_referenced_tickers
from backend.tasks import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Classification helpers (used by SignalConvergenceService as well)
# ---------------------------------------------------------------------------


def _classify_rsi(rsi: float | None) -> str:
    """Classify RSI signal direction.

    Args:
        rsi: RSI value (0-100) or None.

    Returns:
        'bullish' if oversold recovery (<40), 'bearish' if overbought (>70), else 'neutral'.
    """
    if rsi is None:
        return "neutral"
    if rsi < 40:
        return "bullish"
    if rsi > 70:
        return "bearish"
    return "neutral"


def _classify_macd(histogram: float | None, prev_histogram: float | None) -> str:
    """Classify MACD signal direction.

    Args:
        histogram: Current MACD histogram value.
        prev_histogram: Previous period MACD histogram.

    Returns:
        'bullish' if positive and rising, 'bearish' if negative and falling, else 'neutral'.
    """
    if histogram is None:
        return "neutral"
    if histogram > 0 and (prev_histogram is None or histogram > prev_histogram):
        return "bullish"
    if histogram < 0 and (prev_histogram is None or histogram < prev_histogram):
        return "bearish"
    return "neutral"


def _classify_sma(current_price: float | None, sma_200: float | None) -> str:
    """Classify SMA signal direction.

    Args:
        current_price: Current stock price.
        sma_200: 200-day simple moving average.

    Returns:
        'bullish' if >2% above SMA-200, 'bearish' if >2% below, else 'neutral'.
    """
    if current_price is None or sma_200 is None or sma_200 == 0:
        return "neutral"
    pct_diff = (current_price - sma_200) / sma_200
    if pct_diff > 0.02:
        return "bullish"
    if pct_diff < -0.02:
        return "bearish"
    return "neutral"


def _classify_piotroski(score: int | None) -> str:
    """Classify Piotroski F-Score signal direction.

    Args:
        score: Piotroski F-Score (0-9).

    Returns:
        'bullish' if >=6, 'bearish' if <=3, else 'neutral'.
    """
    if score is None:
        return "neutral"
    if score >= 6:
        return "bullish"
    if score <= 3:
        return "bearish"
    return "neutral"


def _classify_forecast(predicted_return: float | None) -> str:
    """Classify forecast signal direction.

    Args:
        predicted_return: Predicted percentage return (e.g., 0.05 = +5%).

    Returns:
        'bullish' if >+3%, 'bearish' if <-3%, else 'neutral'.
    """
    if predicted_return is None:
        return "neutral"
    if predicted_return > 0.03:
        return "bullish"
    if predicted_return < -0.03:
        return "bearish"
    return "neutral"


def _compute_convergence_label(directions: list[str]) -> str:
    """Compute convergence label from signal directions.

    Revised thresholds (per domain review):
    - Strong Bull: 4+ bullish, 0 bearish
    - Weak Bull: 3+ bullish, <=1 bearish
    - Strong Bear: 4+ bearish, 0 bullish
    - Weak Bear: 3+ bearish, <=1 bullish
    - Mixed: everything else

    Args:
        directions: List of signal directions ('bullish', 'bearish', 'neutral').

    Returns:
        Convergence label string.
    """
    bullish = directions.count("bullish")
    bearish = directions.count("bearish")

    if bullish >= 4 and bearish == 0:
        return "strong_bull"
    if bullish >= 3 and bearish <= 1:
        return "weak_bull"
    if bearish >= 4 and bullish == 0:
        return "strong_bear"
    if bearish >= 3 and bullish <= 1:
        return "weak_bear"
    return "mixed"


# ---------------------------------------------------------------------------
# Session context manager helper
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _get_session(
    _db: AsyncSession | None,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session — use injected _db for tests, factory for production.

    Args:
        _db: Optional pre-existing session for test injection.

    Yields:
        AsyncSession for the DB operation.
    """
    if _db is not None:
        yield _db
    else:
        async with async_session_factory() as session:
            yield session


# ---------------------------------------------------------------------------
# Backfill helpers
# ---------------------------------------------------------------------------


async def _bulk_latest_price(
    db: AsyncSession,
    tickers: list[str],
    as_of: date,
) -> dict[str, float]:
    """Bulk-fetch the latest close price per ticker up to and including as_of.

    Uses DISTINCT ON (ticker) with ORDER BY ticker, time DESC so the
    newest price row wins per ticker.

    Args:
        db: Async database session.
        tickers: List of ticker symbols to look up.
        as_of: Date ceiling — only prices on or before this date are considered.

    Returns:
        Dict of ticker → close price (float).
    """
    if not tickers:
        return {}

    # Look back up to 7 days to handle weekends / market holidays
    window_start = datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc) - timedelta(
        days=7
    )
    window_end = datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=timezone.utc)

    stmt = (
        select(StockPrice.ticker, StockPrice.close)
        .distinct(StockPrice.ticker)
        .where(
            StockPrice.ticker.in_(tickers),
            StockPrice.time >= window_start,
            StockPrice.time <= window_end,
        )
        .order_by(StockPrice.ticker, StockPrice.time.desc())
    )
    result = await db.execute(stmt)
    return {row.ticker: float(row.close) for row in result.all()}


async def _bulk_price_on_date(
    db: AsyncSession,
    tickers: list[str],
    target: date,
) -> dict[str, float]:
    """Bulk-fetch the close price per ticker closest to target date.

    Args:
        db: Async database session.
        tickers: List of ticker symbols to look up.
        target: The target date (typically today - 90d or today - 180d).

    Returns:
        Dict of ticker → close price (float).
    """
    return await _bulk_latest_price(db, tickers, as_of=target)


async def _backfill_actual_returns(
    db: AsyncSession,
    tickers: list[str],
    today: date,
    days: int,
) -> int:
    """Back-fill actual_return_{days}d for rows from {days} days ago that have NULL returns.

    Calculates (price_today / price_then) - 1.0 for each eligible row.

    Args:
        db: Async database session.
        tickers: Active ticker universe.
        today: Today's date.
        days: Look-back window — 90 or 180.

    Returns:
        Number of rows updated.
    """
    target_date = today - timedelta(days=days)
    col = (
        SignalConvergenceDaily.actual_return_90d
        if days == 90
        else SignalConvergenceDaily.actual_return_180d
    )
    stmt = select(SignalConvergenceDaily).where(
        SignalConvergenceDaily.date == target_date,
        SignalConvergenceDaily.ticker.in_(tickers),
        col.is_(None),
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return 0

    row_tickers = [r.ticker for r in rows]
    prices_now = await _bulk_latest_price(db, row_tickers, today)
    prices_then = await _bulk_price_on_date(db, row_tickers, target_date)

    updated = 0
    for row in rows:
        p_now = prices_now.get(row.ticker)
        p_then = prices_then.get(row.ticker)
        if p_now and p_then and p_then > 0:
            ret = (p_now / p_then) - 1.0
            if days == 90:
                row.actual_return_90d = ret
            else:
                row.actual_return_180d = ret
            updated += 1
    return updated


# ---------------------------------------------------------------------------
# Core async implementation
# ---------------------------------------------------------------------------


async def _compute_convergence_snapshot_async(
    ticker: str | None = None,
    *,
    _db: AsyncSession | None = None,
) -> dict:
    """Compute and store daily convergence snapshot.

    Accepts a single ticker for targeted runs or None for full-universe mode.
    Also backfills actual_return_90d / actual_return_180d for rows whose
    look-back period has now elapsed.

    Args:
        ticker: If set, process only this ticker. If None, process all universe tickers.
        _db: Injected session for testing. Production callers omit this.

    Returns:
        Status dict with keys: status, computed, backfilled.
    """
    # Lazy import to break circular dependency:
    # signal_convergence imports classification helpers from this module,
    # so we cannot import SignalConvergenceService at the top of this file.
    from backend.services.signal_convergence import SignalConvergenceService  # noqa: PLC0415

    today = datetime.now(timezone.utc).date()
    svc = SignalConvergenceService()

    async with _get_session(_db) as db:
        # Resolve ticker list
        if ticker is not None:
            tickers: list[str] = [ticker]
        else:
            tickers = await get_all_referenced_tickers(db)

        if not tickers:
            return {"status": "no_tickers", "computed": 0, "backfilled": 0}

        # Bulk-fetch convergence data for all tickers
        convergences = await svc.get_bulk_convergence(tickers, db)

        computed = 0
        if convergences:
            # Build upsert rows for tickers that have signal data
            upsert_rows: list[dict] = []
            for tkr, conv in convergences.items():
                # Extract per-signal directions from the signals list
                directions_map: dict[str, str] = {s.signal: s.direction for s in conv.signals}
                values_map: dict[str, float | None] = {s.signal: s.value for s in conv.signals}

                upsert_rows.append(
                    {
                        "date": today,
                        "ticker": tkr,
                        "rsi_direction": directions_map.get("rsi", "neutral"),
                        "macd_direction": directions_map.get("macd", "neutral"),
                        "sma_direction": directions_map.get("sma", "neutral"),
                        "piotroski_direction": directions_map.get("piotroski", "neutral"),
                        "forecast_direction": directions_map.get("forecast", "neutral"),
                        "news_sentiment": values_map.get("news"),
                        "signals_aligned": conv.signals_aligned,
                        "convergence_label": conv.convergence_label,
                        "composite_score": conv.composite_score,
                        "actual_return_90d": None,
                        "actual_return_180d": None,
                    }
                )

            # Upsert all rows in one statement
            ins = pg_insert(SignalConvergenceDaily).values(upsert_rows)
            ins = ins.on_conflict_do_update(
                index_elements=["ticker", "date"],
                set_={
                    "rsi_direction": ins.excluded.rsi_direction,
                    "macd_direction": ins.excluded.macd_direction,
                    "sma_direction": ins.excluded.sma_direction,
                    "piotroski_direction": ins.excluded.piotroski_direction,
                    "forecast_direction": ins.excluded.forecast_direction,
                    "news_sentiment": ins.excluded.news_sentiment,
                    "signals_aligned": ins.excluded.signals_aligned,
                    "convergence_label": ins.excluded.convergence_label,
                    "composite_score": ins.excluded.composite_score,
                },
            )
            await db.execute(ins)
            await db.commit()
            computed = len(convergences)

        # Backfill actual returns for rows from 90 and 180 days ago.
        # Runs regardless of whether today's convergences exist — historical
        # rows may need backfilling even if a ticker has no current signals.
        backfilled = 0
        backfilled += await _backfill_actual_returns(db, tickers, today, days=90)
        backfilled += await _backfill_actual_returns(db, tickers, today, days=180)
        if backfilled:
            await db.commit()

        # Mark each ticker's convergence stage as updated (Spec A ticker_state).
        # Called after the main upsert commit so a crash here never rolls back DB writes.
        # mark_stage_updated is fire-and-forget (errors are logged, not raised).
        for tkr in convergences:
            await mark_stage_updated(tkr, "convergence")

        logger.info(
            "Convergence snapshot complete: computed=%d backfilled=%d",
            computed,
            backfilled,
        )
        return {"status": "ok", "computed": computed, "backfilled": backfilled}


# ---------------------------------------------------------------------------
# Celery task entry point
# ---------------------------------------------------------------------------


@celery_app.task(name="backend.tasks.convergence.compute_convergence_snapshot_task")
def compute_convergence_snapshot_task(ticker: str | None = None) -> dict:
    """Nightly task: compute convergence state for all tracked tickers.

    Also backfills actual_return_90d/180d for rows from 90/180 days ago.

    Args:
        ticker: Optional single ticker for targeted runs. If None, processes all tickers.

    Returns:
        Status dict with computed/backfilled counts.
    """
    return asyncio.run(_compute_convergence_snapshot_async(ticker=ticker))
