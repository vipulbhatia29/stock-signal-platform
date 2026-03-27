"""Pipeline orchestrators — compose atomic services into transactional sequences.

These are the ONLY place where multi-step business workflows are defined.
Routers, tools, and tasks call pipelines for orchestrated operations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.price import StockPrice
from backend.models.user import UserPreference
from backend.services.exceptions import IngestFailedError
from backend.services.recommendations import (
    PortfolioState,
    generate_recommendation,
    store_recommendation,
)
from backend.services.signals import compute_signals, store_signal_snapshot
from backend.services.stock_data import (
    ensure_stock_exists,
    fetch_analyst_data,
    fetch_earnings_history,
    fetch_fundamentals,
    fetch_prices_delta,
    load_prices_df,
    persist_earnings_snapshots,
    persist_enriched_fundamentals,
    update_last_fetched_at,
)

logger = logging.getLogger(__name__)


async def ingest_ticker(
    ticker: str,
    db: AsyncSession,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Full ingest pipeline: ensure stock, fetch prices, compute signals, generate rec.

    Orchestrates the complete ingestion sequence for a single ticker. This is
    the canonical pipeline that routers, tools, and tasks should call instead
    of reimplementing the sequence.

    Steps:
      1. Ensure stock record exists (creates from yfinance if needed)
      2. Fetch price data (delta or full 10Y for new tickers)
      3. Load full price history from DB for signal computation
      4. Fetch and persist fundamentals, analyst data, earnings
      5. Compute technical signals + store snapshot
      6. Update last_fetched_at timestamp
      7. (Optional) Generate and store portfolio-aware recommendation

    Args:
        ticker: Stock symbol (e.g. "AAPL"). Will be uppercased.
        db: Async database session.
        user_id: Optional user UUID. When provided, a portfolio-aware
                 recommendation is generated after signal computation.

    Returns:
        Dict with keys:
          - ticker: uppercased ticker symbol
          - stock_name: company name from Stock record
          - rows_fetched: number of new price rows fetched
          - composite_score: computed composite score (or None)
          - is_new: True if this was the first ingest for this ticker
          - recommendation: RecommendationResult or None

    Raises:
        IngestFailedError: If a critical step (stock lookup or price fetch) fails.
    """
    ticker = ticker.upper().strip()

    # ── Step 1: Ensure stock record exists ────────────────────────────
    try:
        stock = await ensure_stock_exists(ticker, db)
    except ValueError:
        logger.error("Stock lookup failed for %s", ticker)
        raise IngestFailedError(ticker, "ensure_stock_exists")

    is_new = stock.last_fetched_at is None

    # ── Step 2: Fetch price data (delta or full) ──────────────────────
    try:
        delta_df = await fetch_prices_delta(ticker, db)
    except ValueError:
        logger.error("Failed to fetch price data for %s", ticker)
        raise IngestFailedError(ticker, "fetch_prices_delta")

    rows_fetched = len(delta_df) if not delta_df.empty else 0

    # ── Step 3: Load full history from DB for signal computation ──────
    full_df = await load_prices_df(ticker, db)

    # ── Step 4: Fetch fundamentals, analyst data, earnings ────────────
    loop = asyncio.get_event_loop()
    fundamentals = await loop.run_in_executor(None, fetch_fundamentals, ticker)
    piotroski = fundamentals.piotroski_score

    analyst_data = await loop.run_in_executor(None, fetch_analyst_data, ticker)
    await persist_enriched_fundamentals(stock, fundamentals, analyst_data, db)

    earnings = await loop.run_in_executor(None, fetch_earnings_history, ticker)
    await persist_earnings_snapshots(ticker, earnings, db)

    # ── Step 5: Compute signals if we have enough data ────────────────
    composite_score: float | None = None
    signal_result = None
    if not full_df.empty:
        signal_result = compute_signals(ticker, full_df, piotroski_score=piotroski)
        if signal_result.composite_score is not None:
            await store_signal_snapshot(signal_result, db)
            composite_score = signal_result.composite_score

    # ── Step 6: Update last_fetched_at ────────────────────────────────
    await update_last_fetched_at(ticker, db)

    # ── Step 7: Generate portfolio-aware recommendation ───────────────
    recommendation = None
    if (
        user_id is not None
        and signal_result is not None
        and signal_result.composite_score is not None
    ):
        recommendation = await _generate_recommendation_with_context(
            ticker, signal_result, user_id, db
        )

    return {
        "ticker": ticker,
        "stock_name": stock.name,
        "rows_fetched": rows_fetched,
        "composite_score": composite_score,
        "is_new": is_new,
        "recommendation": recommendation,
    }


async def _generate_recommendation_with_context(
    ticker: str,
    signal_result: object,
    user_id: str,
    db: AsyncSession,
) -> object | None:
    """Generate and store a portfolio-aware recommendation.

    Loads portfolio context (positions, user preferences) and generates
    a recommendation. If portfolio context cannot be loaded, falls back
    to a basic (non-portfolio-aware) recommendation.

    Args:
        ticker: Stock symbol.
        signal_result: SignalResult from compute_signals().
        user_id: User UUID string.
        db: Async database session.

    Returns:
        RecommendationResult or None if no price data available.
    """
    from backend.tools.portfolio import get_or_create_portfolio, get_positions_with_pnl

    portfolio_state: PortfolioState | None = None
    max_position_pct = 5.0

    try:
        portfolio = await get_or_create_portfolio(user_id, db)
        positions = await get_positions_with_pnl(portfolio.id, db)
        pos_map = {p.ticker: p for p in positions}
        if ticker in pos_map:
            p = pos_map[ticker]
            portfolio_state = {
                "is_held": True,
                "allocation_pct": p.allocation_pct or 0.0,
            }
        pref_result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        pref = pref_result.scalar_one_or_none()
        if pref is not None:
            max_position_pct = pref.max_position_pct
    except Exception:
        logger.warning(
            "Could not load portfolio context for %s — using basic recommendation",
            ticker,
        )
        portfolio_state = None
        max_position_pct = 5.0

    # Fetch latest price for recommendation
    latest_price_result = await db.execute(
        select(StockPrice)
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.time.desc())
        .limit(1)
    )
    latest_price_row = latest_price_result.scalar_one_or_none()
    if latest_price_row is None:
        return None

    rec = generate_recommendation(
        signal_result,
        current_price=float(latest_price_row.adj_close),
        portfolio_state=portfolio_state,
        max_position_pct=max_position_pct,
    )
    await store_recommendation(rec, user_id, db)
    return rec
