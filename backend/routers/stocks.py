"""Stock, signal, watchlist, and recommendation API endpoints.

This router handles all stock-related API requests. It follows the
layered architecture:

  Router → (validates request, calls service/tool, returns response)
  Tools  → (fetches data, computes signals, generates recommendations)
  DB     → (reads/writes to PostgreSQL + TimescaleDB)

Authentication: All endpoints require a valid JWT token (via get_current_user).
Rate limiting: Inherited from the app-level slowapi configuration.

API Endpoints:
  GET  /stocks/search?q=...            — search stocks by ticker or name
  GET  /stocks/{ticker}/prices         — historical OHLCV prices
  GET  /stocks/{ticker}/signals        — current technical signals
  GET  /watchlist                      — user's watchlist with signal summaries
  POST /watchlist                      — add a ticker to watchlist
  DELETE /watchlist/{ticker}           — remove a ticker from watchlist
  GET  /recommendations                — today's recommendations
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User
from backend.schemas.stock import (
    BollingerResponse,
    MACDResponse,
    PricePeriod,
    PricePointResponse,
    RSIResponse,
    RecommendationResponse,
    ReturnsResponse,
    SMAResponse,
    SignalResponse,
    StockSearchResponse,
    WatchlistAddRequest,
    WatchlistItemResponse,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Stock search
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/search", response_model=list[StockSearchResponse])
async def search_stocks(
    q: str = Query(min_length=1, max_length=20, description="Search query (ticker or company name)"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[Stock]:
    """Search stocks by ticker symbol or company name.

    Performs a case-insensitive prefix match on both the ticker and name
    columns. For example, searching "APP" would match "AAPL" (ticker)
    and "Apple Inc" (name).

    The ILIKE operator is PostgreSQL-specific and does case-insensitive
    pattern matching. The '%' is a wildcard that matches any characters.
    """
    # ILIKE = case-Insensitive LIKE. The f"{q}%" pattern means
    # "starts with q" (prefix match). We search both ticker and name.
    query = (
        select(Stock)
        .where(
            (Stock.ticker.ilike(f"{q}%")) | (Stock.name.ilike(f"%{q}%"))
        )
        .where(Stock.is_active.is_(True))
        .order_by(Stock.ticker)
        .limit(20)  # Cap results to avoid returning thousands of rows
    )

    result = await db.execute(query)
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Price history
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{ticker}/prices", response_model=list[PricePointResponse])
async def get_prices(
    ticker: str,
    period: PricePeriod = Query(default=PricePeriod.ONE_YEAR, description="How far back to fetch prices"),
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
    # ── Verify the ticker exists in our database ─────────────────────
    await _require_stock(ticker, db)

    # ── Calculate the cutoff date based on the period ────────────────
    # Map each period to a timedelta. These are approximate — financial
    # periods aren't exact calendar durations (months have different
    # numbers of days, etc.), but close enough for filtering.
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

    # ── Query prices from the database ───────────────────────────────
    # We filter by ticker AND time, then order by time ascending so the
    # client gets data in chronological order (oldest first).
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
    ticker: str,
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
    await _require_stock(ticker, db)

    # ── Fetch the latest signal snapshot for this ticker ──────────────
    # We order by computed_at DESC and take the first row, giving us
    # the most recent signal computation.
    result = await db.execute(
        select(SignalSnapshot)
        .where(SignalSnapshot.ticker == ticker.upper())
        .order_by(SignalSnapshot.computed_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No signals computed for '{ticker.upper()}'. "
                   "Signals need to be computed first via the signal engine.",
        )

    # ── Check if signals are stale (older than 24 hours) ─────────────
    # Stale signals might not reflect the current market situation.
    # The frontend should show a warning when is_stale=True.
    is_stale = False
    if snapshot.computed_at:
        age = datetime.now(timezone.utc) - snapshot.computed_at.replace(tzinfo=timezone.utc)
        is_stale = age > timedelta(hours=24)

    # ── Build the nested response object ─────────────────────────────
    # We transform the flat database row into a nicely structured JSON
    # response with nested objects for each indicator group.
    return SignalResponse(
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


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist management
# ─────────────────────────────────────────────────────────────────────────────

MAX_WATCHLIST_SIZE = 100  # Maximum tickers per user watchlist


@router.get("/watchlist", response_model=list[WatchlistItemResponse])
async def get_watchlist(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Get the current user's watchlist with stock info.

    Returns all stocks the user has added to their watchlist, including
    the stock name, sector, and when it was added. This endpoint is
    used by the dashboard to show the user's tracked stocks.
    """
    # ── Join Watchlist with Stock to get stock details ────────────────
    # We use a SQL JOIN to combine the watchlist entry (which has the
    # user_id and ticker) with the stock record (which has name, sector).
    result = await db.execute(
        select(Watchlist, Stock)
        .join(Stock, Watchlist.ticker == Stock.ticker)
        .where(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.added_at.desc())
    )
    rows = result.all()

    # Transform the joined rows into response objects
    return [
        {
            "id": watchlist.id,
            "ticker": watchlist.ticker,
            "name": stock.name,
            "sector": stock.sector,
            "added_at": watchlist.added_at,
        }
        for watchlist, stock in rows
    ]


@router.post(
    "/watchlist",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Add a stock ticker to the user's watchlist.

    The ticker must exist in our stocks table. If the user already has
    this ticker on their watchlist, returns 409 Conflict. If the watchlist
    is at the 100-ticker limit, returns 400 Bad Request.
    """
    ticker = body.ticker.upper()

    # ── Verify the stock exists ──────────────────────────────────────
    stock = await _require_stock(ticker, db)

    # ── Check watchlist size limit ───────────────────────────────────
    count_result = await db.execute(
        select(func.count()).select_from(Watchlist).where(
            Watchlist.user_id == current_user.id
        )
    )
    watchlist_count = count_result.scalar_one()

    if watchlist_count >= MAX_WATCHLIST_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Watchlist is full (maximum {MAX_WATCHLIST_SIZE} tickers). "
                   "Remove a ticker before adding a new one.",
        )

    # ── Check for duplicate ──────────────────────────────────────────
    existing = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == current_user.id,
            Watchlist.ticker == ticker,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{ticker}' is already in your watchlist.",
        )

    # ── Create the watchlist entry ───────────────────────────────────
    entry = Watchlist(user_id=current_user.id, ticker=ticker)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {
        "id": entry.id,
        "ticker": entry.ticker,
        "name": stock.name,
        "sector": stock.sector,
        "added_at": entry.added_at,
    }


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    ticker: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove a stock from the user's watchlist.

    Returns 204 No Content on success (standard REST pattern for DELETE).
    Returns 404 if the ticker isn't in the user's watchlist.
    """
    ticker = ticker.upper()

    # ── Find and delete the watchlist entry ───────────────────────────
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == current_user.id,
            Watchlist.ticker == ticker,
        )
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{ticker}' is not in your watchlist.",
        )

    await db.execute(
        delete(Watchlist).where(
            Watchlist.user_id == current_user.id,
            Watchlist.ticker == ticker,
        )
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Recommendations
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/recommendations", response_model=list[RecommendationResponse])
async def get_recommendations(
    action: str | None = Query(
        default=None,
        description="Filter by action: BUY, WATCH, AVOID, HOLD, SELL"
    ),
    confidence: str | None = Query(
        default=None,
        description="Filter by confidence: HIGH, MEDIUM, LOW"
    ),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[RecommendationSnapshot]:
    """Get today's stock recommendations.

    Returns the most recent recommendations for the current user.
    Can be filtered by action (BUY/WATCH/AVOID) and confidence level.

    Only recommendations from the last 24 hours are returned, because
    older recommendations are based on stale signals and may no longer
    be valid.
    """
    # ── Start with a base query for this user's recommendations ──────
    query = (
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.user_id == current_user.id)
    )

    # ── Apply optional filters ───────────────────────────────────────
    # These let the client ask "show me only BUY recommendations" or
    # "show me only HIGH confidence recommendations"
    if action is not None:
        query = query.where(
            RecommendationSnapshot.action == action.upper()
        )

    if confidence is not None:
        query = query.where(
            RecommendationSnapshot.confidence == confidence.upper()
        )

    # ── Only return recent recommendations (last 24 hours) ───────────
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    query = query.where(RecommendationSnapshot.generated_at >= cutoff)

    # ── Order by composite score descending ──────────────────────────
    # Best opportunities (highest scores) appear first
    query = query.order_by(RecommendationSnapshot.composite_score.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _require_stock(ticker: str, db: AsyncSession) -> Stock:
    """Look up a stock by ticker, raising 404 if not found.

    This is a helper used by multiple endpoints to validate that a
    ticker exists in our database before proceeding.

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        db: Async database session.

    Returns:
        The Stock ORM object.

    Raises:
        HTTPException: 404 if the ticker doesn't exist.
    """
    result = await db.execute(
        select(Stock).where(Stock.ticker == ticker.upper())
    )
    stock = result.scalar_one_or_none()

    if stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock '{ticker.upper()}' not found. "
                   "Make sure the ticker is correct and has been added to the system.",
        )

    return stock
