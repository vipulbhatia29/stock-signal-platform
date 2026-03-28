"""Stock data read endpoints — prices, signals, fundamentals, news, intelligence.

These endpoints return stock data for individual tickers. All require JWT
authentication and a valid ticker in the database.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.price import StockPrice
from backend.models.user import User
from backend.routers.stocks._helpers import require_stock
from backend.schemas.stock import (
    BollingerResponse,
    FundamentalsResponse,
    MACDResponse,
    PiotroskiBreakdown,
    PricePeriod,
    PricePointResponse,
    ReturnsResponse,
    RSIResponse,
    SignalResponse,
    SMAResponse,
)
from backend.services.signals import get_latest_signals as get_latest_signals_svc
from backend.services.stock_data import fetch_fundamentals
from backend.validation import TickerPath

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Price history
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/prices", response_model=list[PricePointResponse])
async def get_prices(
    ticker: TickerPath,
    period: PricePeriod = Query(
        default=PricePeriod.ONE_YEAR, description="How far back to fetch prices"
    ),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[StockPrice]:
    """Get historical OHLCV prices for a stock.

    Returns daily price data from our database. The 'period' parameter
    controls how far back to look:
      - 1mo: last month (good for short-term trends)
      - 1y:  last year (good for seeing seasonal patterns)
      - 10y: last decade (good for long-term performance)

    The cutoff date is calculated by subtracting the period from today.
    For example, if period=1y and today is 2026-03-01, we return all
    prices from 2025-03-01 onwards.
    """
    await require_stock(ticker, db)

    period_days = {
        PricePeriod.ONE_MONTH: 30,
        PricePeriod.THREE_MONTHS: 90,
        PricePeriod.SIX_MONTHS: 180,
        PricePeriod.ONE_YEAR: 365,
        PricePeriod.TWO_YEARS: 730,
        PricePeriod.FIVE_YEARS: 1825,
        PricePeriod.TEN_YEARS: 3650,
    }
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days[period])

    result = await db.execute(
        select(StockPrice)
        .where(StockPrice.ticker == ticker.upper())
        .where(StockPrice.time >= cutoff)
        .order_by(StockPrice.time.asc())
    )

    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Signals
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/signals", response_model=SignalResponse)
async def get_signals(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    """Get the latest technical signals for a stock.

    Returns the most recently computed signal snapshot, which includes:
      - RSI: momentum indicator (oversold/neutral/overbought)
      - MACD: trend direction (bullish/bearish)
      - SMA: long-term trend (golden cross, death cross, etc.)
      - Bollinger Bands: volatility position
      - Returns: annualized return, volatility, Sharpe ratio
      - Composite Score: overall signal strength (0-10)

    Signals are flagged as "stale" if they're older than 24 hours,
    meaning they should be recomputed for accurate recommendations.
    """
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:signals:{ticker.upper()}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return SignalResponse.model_validate_json(cached)

    await require_stock(ticker, db)

    snapshot = await get_latest_signals_svc(ticker, db)

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No signals computed for '{ticker.upper()}'. "
            "Signals need to be computed first via the signal engine.",
        )

    is_stale = False
    if snapshot.computed_at:
        age = datetime.now(timezone.utc) - snapshot.computed_at.replace(tzinfo=timezone.utc)
        is_stale = age > timedelta(hours=24)

    response = SignalResponse(
        ticker=snapshot.ticker,
        computed_at=snapshot.computed_at,
        rsi=RSIResponse(value=snapshot.rsi_value, signal=snapshot.rsi_signal),
        macd=MACDResponse(
            value=snapshot.macd_value,
            histogram=snapshot.macd_histogram,
            signal=snapshot.macd_signal_label,
        ),
        sma=SMAResponse(
            sma_50=snapshot.sma_50,
            sma_200=snapshot.sma_200,
            signal=snapshot.sma_signal,
        ),
        bollinger=BollingerResponse(
            upper=snapshot.bb_upper,
            lower=snapshot.bb_lower,
            position=snapshot.bb_position,
        ),
        returns=ReturnsResponse(
            annual_return=snapshot.annual_return,
            volatility=snapshot.volatility,
            sharpe=snapshot.sharpe_ratio,
        ),
        composite_score=snapshot.composite_score,
        is_stale=is_stale,
    )
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.STANDARD)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/fundamentals", response_model=FundamentalsResponse)
async def get_fundamentals(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> FundamentalsResponse:
    """Get fundamental financial metrics for a stock.

    Returns enriched fundamental data from the database (materialized
    during ingestion) including valuation ratios, growth rates, margins,
    analyst targets, and Piotroski F-Score.

    Note: Data is refreshed on each ingest. If fields are null, run
    ingest first. ETFs, SPACs, or very new listings may have missing data.
    """
    stock = await require_stock(ticker, db)
    t = ticker.upper().strip()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:fundamentals:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return FundamentalsResponse.model_validate_json(cached)

    result = await asyncio.get_event_loop().run_in_executor(None, fetch_fundamentals, t)

    response = FundamentalsResponse(
        ticker=result.ticker,
        pe_ratio=result.pe_ratio,
        peg_ratio=result.peg_ratio,
        fcf_yield=result.fcf_yield,
        debt_to_equity=result.debt_to_equity,
        piotroski_score=result.piotroski_score,
        piotroski_breakdown=PiotroskiBreakdown(**(result.piotroski_breakdown or {})),
        revenue_growth=stock.revenue_growth,
        gross_margins=stock.gross_margins,
        operating_margins=stock.operating_margins,
        profit_margins=stock.profit_margins,
        return_on_equity=stock.return_on_equity,
        market_cap=stock.market_cap,
        analyst_target_mean=stock.analyst_target_mean,
        analyst_target_high=stock.analyst_target_high,
        analyst_target_low=stock.analyst_target_low,
        analyst_buy=stock.analyst_buy,
        analyst_hold=stock.analyst_hold,
        analyst_sell=stock.analyst_sell,
    )
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.STABLE)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# News
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/news")
async def get_stock_news(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get recent news articles for a stock from multiple sources."""
    import asyncio
    from datetime import datetime, timezone

    from backend.schemas.intelligence import StockNewsResponse
    from backend.services.cache import CacheTier
    from backend.tools.news import (
        fetch_google_news_rss,
        fetch_yfinance_news,
        merge_and_deduplicate,
    )

    await require_stock(ticker, db)
    t = ticker.upper()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:news:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockNewsResponse.model_validate_json(cached)

    yf_articles = await asyncio.to_thread(fetch_yfinance_news, t)
    google_articles = await fetch_google_news_rss(t)
    merged = merge_and_deduplicate(yf_articles + google_articles)

    response = StockNewsResponse(
        ticker=t,
        articles=merged,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/intelligence")
async def get_stock_intelligence(
    ticker: TickerPath,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """Get analyst upgrades, insider transactions, earnings calendar, EPS revisions."""
    import asyncio
    from datetime import datetime, timezone

    from backend.schemas.intelligence import StockIntelligenceResponse
    from backend.services.cache import CacheTier
    from backend.tools.intelligence import (
        fetch_eps_revisions,
        fetch_insider_transactions,
        fetch_next_earnings_date,
        fetch_upgrades_downgrades,
    )

    await require_stock(ticker, db)
    t = ticker.upper()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:intelligence:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockIntelligenceResponse.model_validate_json(cached)

    upgrades, insider, earnings, eps = await asyncio.gather(
        asyncio.to_thread(fetch_upgrades_downgrades, t),
        asyncio.to_thread(fetch_insider_transactions, t),
        asyncio.to_thread(fetch_next_earnings_date, t),
        asyncio.to_thread(fetch_eps_revisions, t),
    )

    response = StockIntelligenceResponse(
        ticker=t,
        upgrades_downgrades=upgrades,
        insider_transactions=insider,
        next_earnings_date=earnings,
        eps_revisions=eps,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response
