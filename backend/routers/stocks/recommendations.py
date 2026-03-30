"""Recommendation and bulk signal endpoints.

Delegates to ``backend.services.signals`` and ``backend.services.recommendations``
for business logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.recommendation import RecommendationSnapshot
from backend.models.stock import Stock
from backend.models.user import User
from backend.routers.stocks._helpers import require_stock
from backend.schemas.stock import (
    BulkSignalItem,
    BulkSignalsResponse,
    RecommendationListResponse,
    RecommendationResponse,
    SignalHistoryItem,
)
from backend.services.signals import (
    get_bulk_signals as get_bulk_signals_svc,
)
from backend.services.signals import (
    get_signal_history as get_signal_history_svc,
)
from backend.validation import (
    ActionQuery,
    ConfidenceQuery,
    MacdStateQuery,
    RsiStateQuery,
    SectorQuery,
    TickerPath,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Recommendations
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/recommendations", response_model=RecommendationListResponse)
async def get_recommendations(
    request: Request,
    action: ActionQuery = None,
    confidence: ConfidenceQuery = None,
    limit: int = Query(default=50, ge=1, le=200, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RecommendationListResponse:
    """Get today's stock recommendations.

    Returns the most recent recommendations for the current user.
    Can be filtered by action (BUY/WATCH/AVOID) and confidence level.

    Only recommendations from the last 24 hours are returned, because
    older recommendations are based on stale signals and may no longer
    be valid.
    """
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"user:{current_user.id}:recommendations:{action or 'all'}:{confidence or 'all'}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return RecommendationListResponse.model_validate_json(cached)

    base_filter = select(RecommendationSnapshot).where(
        RecommendationSnapshot.user_id == current_user.id
    )

    if action is not None:
        base_filter = base_filter.where(RecommendationSnapshot.action == action.upper())

    if confidence is not None:
        base_filter = base_filter.where(RecommendationSnapshot.confidence == confidence.upper())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    base_filter = base_filter.where(RecommendationSnapshot.generated_at >= cutoff)

    # Count total before pagination
    count_result = await db.execute(select(func.count()).select_from(base_filter.subquery()))
    total = count_result.scalar_one()

    # Main query with JOIN to get stock name
    query = (
        select(RecommendationSnapshot, Stock.name)
        .join(Stock, RecommendationSnapshot.ticker == Stock.ticker, isouter=True)
        .where(RecommendationSnapshot.user_id == current_user.id)
    )

    if action is not None:
        query = query.where(RecommendationSnapshot.action == action.upper())
    if confidence is not None:
        query = query.where(RecommendationSnapshot.confidence == confidence.upper())
    query = query.where(RecommendationSnapshot.generated_at >= cutoff)

    query = query.order_by(RecommendationSnapshot.composite_score.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    rows = result.all()

    recommendations = []
    for row in rows:
        snapshot = row[0]
        stock_name = row[1]
        rec_dict = {c.key: getattr(snapshot, c.key) for c in snapshot.__table__.columns}
        rec_dict["name"] = stock_name
        recommendations.append(RecommendationResponse.model_validate(rec_dict))

    response = RecommendationListResponse(
        recommendations=recommendations,
        total=total,
    )
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Bulk signals (screener)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/signals/bulk", response_model=BulkSignalsResponse)
async def get_bulk_signals(
    index_id: str | None = Query(default=None, description="Filter by index ID"),
    tickers: str | None = Query(default=None, description="Comma-separated ticker list"),
    rsi_state: RsiStateQuery = None,
    macd_state: MacdStateQuery = None,
    sector: SectorQuery = None,
    score_min: float | None = Query(default=None, ge=0, le=10),
    score_max: float | None = Query(default=None, ge=0, le=10),
    sharpe_min: float | None = Query(default=None, description="Minimum Sharpe ratio filter"),
    sort_by: str = Query(default="composite_score", description="Field to sort by"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> BulkSignalsResponse:
    """Get latest signals for multiple stocks (screener endpoint).

    Returns the most recent signal snapshot per ticker, with filtering
    by index, tickers, RSI state, MACD state, sector, and composite score range.
    Results are paginated and sortable.
    """
    tickers_list = (
        [t.strip().upper() for t in tickers.split(",") if t.strip()][:200] if tickers else None
    )

    total, rows = await get_bulk_signals_svc(
        db,
        index_id=index_id,
        tickers=tickers_list,
        rsi_state=rsi_state,
        macd_state=macd_state,
        sector=sector,
        score_min=score_min,
        score_max=score_max,
        sharpe_min=sharpe_min,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    items = [
        BulkSignalItem(
            ticker=row.ticker,
            name=row.name,
            sector=row.stock_sector,
            composite_score=row.composite_score,
            rsi_value=row.rsi_value,
            rsi_signal=row.rsi_signal,
            macd_signal=row.macd_signal_label,
            sma_signal=row.sma_signal,
            bb_position=row.bb_position,
            annual_return=row.annual_return,
            volatility=row.volatility,
            sharpe_ratio=row.sharpe_ratio,
            computed_at=row.computed_at,
            is_stale=(
                row.computed_at.replace(tzinfo=timezone.utc) < stale_cutoff
                if row.computed_at
                else True
            ),
            price_history=row.price_history,
        )
        for row in rows
    ]

    return BulkSignalsResponse(total=total, items=items)


# ─────────────────────────────────────────────────────────────────────────────
# Signal history
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{ticker}/signals/history", response_model=list[SignalHistoryItem])
async def get_signal_history(
    ticker: TickerPath,
    days: int = Query(default=90, ge=1, le=365, description="Number of days of history"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Get historical signal snapshots for a ticker.

    Returns chronological signal data for charting signal trends over time.
    Default is last 90 days, maximum 365 days.
    """
    await require_stock(ticker, db)

    snapshots = await get_signal_history_svc(ticker, db, days=days, limit=limit)

    return [
        {
            "computed_at": s.computed_at,
            "composite_score": s.composite_score,
            "rsi_value": s.rsi_value,
            "rsi_signal": s.rsi_signal,
            "macd_value": s.macd_value,
            "macd_signal": s.macd_signal_label,
            "sma_signal": s.sma_signal,
            "bb_position": s.bb_position,
        }
        for s in snapshots
    ]
