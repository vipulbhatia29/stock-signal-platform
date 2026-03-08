"""Stock index API endpoints.

Endpoints:
  GET /indexes             — list all indexes with stock counts
  GET /indexes/{slug}/stocks — list stocks in an index with signal summaries
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock
from backend.models.user import User
from backend.schemas.index import IndexResponse, IndexStockItem, IndexStocksResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[IndexResponse])
async def list_indexes(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all stock indexes with their member counts."""
    query = (
        select(
            StockIndex.id,
            StockIndex.name,
            StockIndex.slug,
            StockIndex.description,
            func.count(StockIndexMembership.id).label("stock_count"),
        )
        .outerjoin(StockIndexMembership, StockIndex.id == StockIndexMembership.index_id)
        .group_by(StockIndex.id)
        .order_by(StockIndex.name)
    )
    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "stock_count": row.stock_count,
        }
        for row in rows
    ]


@router.get("/{slug}/stocks", response_model=IndexStocksResponse)
async def get_index_stocks(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> IndexStocksResponse:
    """List stocks in a specific index with latest price and signal summary.

    Returns paginated results with each stock's most recent price and
    composite signal score.
    """
    # Verify index exists
    idx_result = await db.execute(select(StockIndex).where(StockIndex.slug == slug))
    index = idx_result.scalar_one_or_none()
    if index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Index '{slug}' not found.",
        )

    # Count total members
    count_result = await db.execute(
        select(func.count())
        .select_from(StockIndexMembership)
        .where(StockIndexMembership.index_id == index.id)
    )
    total = count_result.scalar_one()

    # Latest signal per ticker via subquery
    latest_signal = (
        select(
            SignalSnapshot.ticker,
            SignalSnapshot.composite_score,
            SignalSnapshot.rsi_signal,
            SignalSnapshot.macd_signal_label,
            func.row_number()
            .over(
                partition_by=SignalSnapshot.ticker,
                order_by=SignalSnapshot.computed_at.desc(),
            )
            .label("rn"),
        )
    ).subquery("latest_signal")

    # Latest price per ticker via subquery
    latest_price = (
        select(
            StockPrice.ticker,
            StockPrice.adj_close,
            func.row_number()
            .over(
                partition_by=StockPrice.ticker,
                order_by=StockPrice.time.desc(),
            )
            .label("rn"),
        )
    ).subquery("latest_price")

    # Main query: stocks in index + latest signal + latest price
    query = (
        select(
            Stock.ticker,
            Stock.name,
            Stock.sector,
            Stock.exchange,
            latest_price.c.adj_close.label("latest_price"),
            latest_signal.c.composite_score,
            latest_signal.c.rsi_signal,
            latest_signal.c.macd_signal_label.label("macd_signal"),
        )
        .join(StockIndexMembership, Stock.ticker == StockIndexMembership.ticker)
        .outerjoin(
            latest_signal,
            (Stock.ticker == latest_signal.c.ticker) & (latest_signal.c.rn == 1),
        )
        .outerjoin(
            latest_price,
            (Stock.ticker == latest_price.c.ticker) & (latest_price.c.rn == 1),
        )
        .where(StockIndexMembership.index_id == index.id)
        .order_by(Stock.ticker)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    rows = result.all()

    items = [
        IndexStockItem(
            ticker=row.ticker,
            name=row.name,
            sector=row.sector,
            exchange=row.exchange,
            latest_price=row.latest_price,
            composite_score=row.composite_score,
            rsi_signal=row.rsi_signal,
            macd_signal=row.macd_signal,
        )
        for row in rows
    ]

    return IndexStocksResponse(
        index_name=index.name,
        total=total,
        items=items,
    )
