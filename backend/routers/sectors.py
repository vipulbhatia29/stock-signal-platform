"""Sectors router — sector-level analytics, stock drill-down, and correlation."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from urllib.parse import unquote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.portfolio import Portfolio, Position
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User
from backend.schemas.sectors import (
    CorrelationResponse,
    ExcludedTicker,
    SectorStock,
    SectorStocksResponse,
    SectorSummary,
    SectorSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
MAX_CORRELATION_TICKERS = 15
MIN_CORRELATION_DATAPOINTS = 30
_UNKNOWN_SECTOR = "Unknown"


class ScopeEnum(StrEnum):
    """Scope filter for sector summaries."""

    portfolio = "portfolio"
    watchlist = "watchlist"
    all = "all"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_user_tickers(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[set[str], set[str]]:
    """Return (held_tickers, watched_tickers) for the user."""
    # Portfolio positions
    portfolio_q = (
        select(Position.ticker)
        .join(Portfolio, Portfolio.id == Position.portfolio_id)
        .where(Portfolio.user_id == user_id, Position.closed_at.is_(None))
    )
    held_result = await db.execute(portfolio_q)
    held_tickers = {row[0] for row in held_result.all()}

    # Watchlist
    watch_q = select(Watchlist.ticker).where(Watchlist.user_id == user_id)
    watch_result = await db.execute(watch_q)
    watched_tickers = {row[0] for row in watch_result.all()}

    return held_tickers, watched_tickers


async def _latest_signal_subquery() -> select:
    """Subquery for the latest signal snapshot per ticker."""
    return (
        select(
            SignalSnapshot.ticker,
            func.max(SignalSnapshot.computed_at).label("max_computed_at"),
        )
        .group_by(SignalSnapshot.ticker)
        .subquery()
    )


async def _latest_price_subquery() -> select:
    """Subquery for the latest price per ticker."""
    return (
        select(
            StockPrice.ticker,
            func.max(StockPrice.time).label("max_time"),
        )
        .group_by(StockPrice.ticker)
        .subquery()
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /sectors
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=SectorSummaryResponse,
    summary="List all sectors with summary stats",
    description="Returns sectors with stock count, average composite score, "
    "average annual return, and portfolio allocation percentage.",
)
async def list_sectors(
    request: Request,
    scope: ScopeEnum = Query(ScopeEnum.all, description="Filter scope"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> SectorSummaryResponse:
    """Aggregate sector-level statistics.

    Args:
        request: FastAPI request (used for cache access).
        scope: Filter by portfolio, watchlist, or all stocks.
        current_user: Authenticated user.
        db: Async database session.

    Returns:
        SectorSummaryResponse with per-sector stats.
    """
    cache = getattr(request.app.state, "cache", None)
    cache_key = "app:sectors:summary"
    if cache:
        from backend.services.cache import CacheTier

        cached = await cache.get(cache_key)
        if cached:
            return SectorSummaryResponse.model_validate_json(cached)

    held_tickers, watched_tickers = await _get_user_tickers(current_user.id, db)

    # Latest signal per ticker (for composite_score + annual_return)
    latest_sig = await _latest_signal_subquery()

    # All active stocks with their latest signal
    base_q = (
        select(
            func.coalesce(Stock.sector, _UNKNOWN_SECTOR).label("sector"),
            Stock.ticker,
            SignalSnapshot.composite_score,
            SignalSnapshot.annual_return,
        )
        .outerjoin(
            latest_sig,
            Stock.ticker == latest_sig.c.ticker,
        )
        .outerjoin(
            SignalSnapshot,
            (SignalSnapshot.ticker == Stock.ticker)
            & (SignalSnapshot.computed_at == latest_sig.c.max_computed_at),
        )
        .where(Stock.is_active.is_(True))
    )

    result = await db.execute(base_q)
    rows = result.all()

    # Build portfolio market values for allocation_pct
    portfolio_values: dict[str, float] = {}
    total_portfolio_value = 0.0
    if scope in (ScopeEnum.portfolio, ScopeEnum.all):
        portfolio_q = select(Portfolio.id).where(Portfolio.user_id == current_user.id)
        pf_result = await db.execute(portfolio_q)
        pf_row = pf_result.scalar_one_or_none()

        if pf_row is not None:
            portfolio_id = pf_row
            # Get positions with latest prices
            latest_price = await _latest_price_subquery()
            pos_q = (
                select(
                    Position.ticker,
                    Position.shares,
                    StockPrice.adj_close,
                    func.coalesce(Stock.sector, _UNKNOWN_SECTOR).label("sector"),
                )
                .join(Stock, Stock.ticker == Position.ticker)
                .outerjoin(
                    latest_price,
                    Position.ticker == latest_price.c.ticker,
                )
                .outerjoin(
                    StockPrice,
                    (StockPrice.ticker == Position.ticker)
                    & (StockPrice.time == latest_price.c.max_time),
                )
                .where(
                    Position.portfolio_id == portfolio_id,
                    Position.closed_at.is_(None),
                )
            )
            pos_result = await db.execute(pos_q)
            for pos_row in pos_result.all():
                ticker, shares, price, sector = pos_row
                mv = float(shares) * float(price) if price else 0.0
                portfolio_values[sector] = portfolio_values.get(sector, 0.0) + mv
                total_portfolio_value += mv

    # Aggregate by sector
    sector_data: dict[str, dict] = {}
    for sector, ticker, comp_score, annual_ret in rows:
        if sector not in sector_data:
            sector_data[sector] = {
                "sector": sector,
                "tickers": [],
                "scores": [],
                "returns": [],
                "your_count": 0,
            }
        sd = sector_data[sector]
        sd["tickers"].append(ticker)
        if comp_score is not None:
            sd["scores"].append(float(comp_score))
        if annual_ret is not None:
            sd["returns"].append(float(annual_ret))

        # Count user's stocks based on scope
        if scope == ScopeEnum.portfolio and ticker in held_tickers:
            sd["your_count"] += 1
        elif scope == ScopeEnum.watchlist and ticker in watched_tickers:
            sd["your_count"] += 1
        elif scope == ScopeEnum.all and ticker in (held_tickers | watched_tickers):
            sd["your_count"] += 1

    # Build response
    summaries: list[SectorSummary] = []
    for sector, sd in sector_data.items():
        avg_score = round(sum(sd["scores"]) / len(sd["scores"]), 2) if sd["scores"] else None
        avg_ret = round(sum(sd["returns"]) / len(sd["returns"]), 2) if sd["returns"] else None
        alloc_pct = (
            round(portfolio_values.get(sector, 0.0) / total_portfolio_value * 100, 2)
            if total_portfolio_value > 0
            else None
        )

        summaries.append(
            SectorSummary(
                sector=sector,
                stock_count=len(sd["tickers"]),
                avg_composite_score=avg_score,
                avg_return_pct=avg_ret,
                your_stock_count=sd["your_count"],
                allocation_pct=alloc_pct,
            )
        )

    # Sort: by allocation_pct descending (None last)
    summaries.sort(key=lambda s: s.allocation_pct or -1, reverse=True)

    response = SectorSummaryResponse(sectors=summaries)
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), tier=CacheTier.STANDARD)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# GET /sectors/{sector}/stocks
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{sector}/stocks",
    response_model=SectorStocksResponse,
    summary="List stocks in a sector",
    description="Returns top 20 stocks by composite score plus user's held/watched stocks.",
)
async def get_sector_stocks(
    sector: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> SectorStocksResponse:
    """Drill-down into a specific sector's stocks.

    Args:
        sector: URL-encoded sector name.
        request: FastAPI request (used for cache access).
        current_user: Authenticated user.
        db: Async database session.

    Returns:
        SectorStocksResponse with stocks sorted by relevance.
    """
    decoded_sector = unquote(sector)
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:sectors:{decoded_sector}:stocks"
    if cache:
        from backend.services.cache import CacheTier

        cached = await cache.get(cache_key)
        if cached:
            return SectorStocksResponse.model_validate_json(cached)
    held_tickers, watched_tickers = await _get_user_tickers(current_user.id, db)

    # Check sector exists
    if decoded_sector == _UNKNOWN_SECTOR:
        sector_filter = Stock.sector.is_(None)
    else:
        sector_filter = Stock.sector == decoded_sector

    count_result = await db.execute(
        select(func.count()).select_from(Stock).where(sector_filter, Stock.is_active.is_(True))
    )
    if count_result.scalar() == 0:
        raise HTTPException(status_code=404, detail="Sector not found")

    # Latest signal + latest price subqueries
    latest_sig = await _latest_signal_subquery()
    latest_price = await _latest_price_subquery()

    # Query all stocks in sector with their latest signal and price
    stocks_q = (
        select(
            Stock.ticker,
            Stock.name,
            SignalSnapshot.composite_score,
            SignalSnapshot.annual_return,
            StockPrice.adj_close,
        )
        .outerjoin(latest_sig, Stock.ticker == latest_sig.c.ticker)
        .outerjoin(
            SignalSnapshot,
            (SignalSnapshot.ticker == Stock.ticker)
            & (SignalSnapshot.computed_at == latest_sig.c.max_computed_at),
        )
        .outerjoin(latest_price, Stock.ticker == latest_price.c.ticker)
        .outerjoin(
            StockPrice,
            (StockPrice.ticker == Stock.ticker) & (StockPrice.time == latest_price.c.max_time),
        )
        .where(sector_filter, Stock.is_active.is_(True))
        .order_by(SignalSnapshot.composite_score.desc().nullslast())
    )
    result = await db.execute(stocks_q)
    all_rows = result.all()

    # Build response — user's stocks always included, then top 20
    user_tickers = held_tickers | watched_tickers
    user_stocks: list[SectorStock] = []
    other_stocks: list[SectorStock] = []

    for ticker, name, comp_score, annual_ret, price in all_rows:
        stock = SectorStock(
            ticker=ticker,
            name=name,
            composite_score=round(float(comp_score), 2) if comp_score is not None else None,
            current_price=round(float(price), 2) if price is not None else None,
            return_pct=round(float(annual_ret), 2) if annual_ret is not None else None,
            is_held=ticker in held_tickers,
            is_watched=ticker in watched_tickers,
        )
        if ticker in user_tickers:
            user_stocks.append(stock)
        else:
            other_stocks.append(stock)

    # Sort user stocks: held first, then watched, then by score desc
    user_stocks.sort(
        key=lambda s: (not s.is_held, not s.is_watched, -(s.composite_score or -1)),
    )

    # Combine: user stocks + top 20 others (deduplication already handled)
    combined = user_stocks + other_stocks[:20]

    response = SectorStocksResponse(sector=decoded_sector, stocks=combined)
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), tier=CacheTier.STANDARD)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# GET /sectors/{sector}/correlation
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{sector}/correlation",
    response_model=CorrelationResponse,
    summary="Compute price correlation matrix for sector stocks",
    description="Returns a symmetric correlation matrix of daily returns "
    "for the given tickers within a sector.",
)
async def get_sector_correlation(
    sector: str,
    tickers: str | None = Query(
        None,
        description="Comma-separated tickers (default: user's portfolio+watchlist in sector)",
    ),
    period_days: int = Query(90, ge=7, le=365, description="Lookback period in days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> CorrelationResponse:
    """Compute daily-returns correlation matrix for tickers in a sector.

    Args:
        sector: URL-encoded sector name.
        tickers: Optional comma-separated ticker list.
        period_days: Lookback window in days.
        current_user: Authenticated user.
        db: Async database session.

    Returns:
        CorrelationResponse with symmetric matrix and excluded tickers.
    """
    decoded_sector = unquote(sector)

    # Determine ticker list
    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        # Default: user's portfolio + watchlist stocks in this sector
        held_tickers, watched_tickers = await _get_user_tickers(current_user.id, db)
        all_user_tickers = held_tickers | watched_tickers

        if decoded_sector == _UNKNOWN_SECTOR:
            sector_filter = Stock.sector.is_(None)
        else:
            sector_filter = Stock.sector == decoded_sector

        user_sector_q = select(Stock.ticker).where(
            sector_filter, Stock.is_active.is_(True), Stock.ticker.in_(all_user_tickers)
        )
        user_result = await db.execute(user_sector_q)
        ticker_list = [row[0] for row in user_result.all()]

    # Validation 1: max tickers
    if len(ticker_list) > MAX_CORRELATION_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_CORRELATION_TICKERS} tickers allowed for correlation",
        )

    if len(ticker_list) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 tickers are required for correlation",
        )

    # Validation 2: all tickers belong to sector
    if decoded_sector == _UNKNOWN_SECTOR:
        sector_filter = Stock.sector.is_(None)
    else:
        sector_filter = Stock.sector == decoded_sector

    valid_q = select(Stock.ticker).where(
        sector_filter, Stock.is_active.is_(True), Stock.ticker.in_(ticker_list)
    )
    valid_result = await db.execute(valid_q)
    valid_tickers = {row[0] for row in valid_result.all()}

    invalid_tickers = set(ticker_list) - valid_tickers
    if invalid_tickers:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tickers not in sector '{decoded_sector}': {', '.join(sorted(invalid_tickers))}"
            ),
        )

    # Fetch price data
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
    price_q = (
        select(StockPrice.ticker, StockPrice.time, StockPrice.adj_close)
        .where(
            StockPrice.ticker.in_(ticker_list),
            StockPrice.time >= cutoff,
        )
        .order_by(StockPrice.time)
    )
    price_result = await db.execute(price_q)
    price_rows = price_result.all()

    # Build DataFrame
    price_data: dict[str, list[tuple]] = {}
    for ticker, time, adj_close in price_rows:
        if ticker not in price_data:
            price_data[ticker] = []
        price_data[ticker].append((time, float(adj_close)))

    # Filter tickers with insufficient data
    excluded: list[ExcludedTicker] = []
    sufficient_tickers: list[str] = []
    for ticker in ticker_list:
        data_points = len(price_data.get(ticker, []))
        if data_points < MIN_CORRELATION_DATAPOINTS:
            excluded.append(
                ExcludedTicker(
                    ticker=ticker,
                    reason=f"Only {data_points} data points (minimum {MIN_CORRELATION_DATAPOINTS})",
                )
            )
        else:
            sufficient_tickers.append(ticker)

    if len(sufficient_tickers) < 2:
        raise HTTPException(
            status_code=400,
            detail="Fewer than 2 tickers have sufficient price data for correlation",
        )

    # Build pandas DataFrame of daily returns
    series_dict: dict[str, pd.Series] = {}
    for ticker in sufficient_tickers:
        times, prices = zip(*price_data[ticker])
        # Normalize to date to align across tickers
        date_index = pd.DatetimeIndex(times).normalize()
        s = pd.Series(data=prices, index=date_index, name=ticker)
        # Deduplicate dates (keep last)
        s = s[~s.index.duplicated(keep="last")]
        series_dict[ticker] = s

    df = pd.DataFrame(series_dict)
    # Drop rows with any NaN (dates where not all tickers have data)
    df = df.dropna()
    # Compute daily returns correlation
    returns_df = df.pct_change(fill_method=None).dropna()
    corr_matrix = returns_df.corr()

    # Replace NaN with 0.0 (can happen if a ticker has constant price)
    corr_matrix = corr_matrix.fillna(0.0)

    # Convert to list[list[float]]
    matrix = [
        [round(float(corr_matrix.iloc[i, j]), 4) for j in range(len(sufficient_tickers))]
        for i in range(len(sufficient_tickers))
    ]

    return CorrelationResponse(
        sector=decoded_sector,
        tickers=sufficient_tickers,
        matrix=matrix,
        period_days=period_days,
        excluded_tickers=excluded,
    )
