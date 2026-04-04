"""News sentiment API — daily sentiment scores and article metadata."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.news_sentiment import NewsArticle, NewsSentimentDaily
from backend.models.user import User
from backend.schemas.sentiment import (
    ArticleListResponse,
    ArticleSummaryResponse,
    BulkSentimentResponse,
    DailySentimentResponse,
    MacroSentimentResponse,
    SentimentTimeseriesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sentiment", tags=["sentiment"])

_MACRO_TICKER = "__MACRO__"


def _row_to_daily(row: NewsSentimentDaily) -> DailySentimentResponse:
    """Convert a NewsSentimentDaily ORM row to a response schema.

    Args:
        row: ORM instance from news_sentiment_daily.

    Returns:
        DailySentimentResponse populated from the ORM row.
    """
    return DailySentimentResponse(
        date=row.date,
        ticker=row.ticker,
        stock_sentiment=row.stock_sentiment,
        sector_sentiment=row.sector_sentiment,
        macro_sentiment=row.macro_sentiment,
        article_count=row.article_count,
        confidence=row.confidence,
        dominant_event_type=row.dominant_event_type,
        rationale_summary=row.rationale_summary,
        quality_flag=row.quality_flag,
    )


# ---------------------------------------------------------------------------
# Literal routes MUST come before /{ticker} to avoid FastAPI path shadowing.
# ---------------------------------------------------------------------------


@router.get(
    "/bulk",
    response_model=BulkSentimentResponse,
    status_code=status.HTTP_200_OK,
    summary="Latest sentiment for multiple tickers",
    description=(
        "Returns the most recent daily sentiment row for each requested ticker. "
        "Pass tickers as a comma-separated string, e.g. `?tickers=AAPL,MSFT,GOOGL`."
    ),
)
async def get_bulk_sentiment(
    tickers: Annotated[
        str,
        Query(description="Comma-separated list of ticker symbols, e.g. AAPL,MSFT"),
    ],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> BulkSentimentResponse:
    """Fetch the latest sentiment row for each requested ticker.

    Args:
        tickers: Comma-separated ticker symbols.
        current_user: Authenticated user (injected by dependency).
        session: Async SQLAlchemy session (injected by dependency).

    Returns:
        BulkSentimentResponse containing one row per ticker.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one ticker is required.",
        )
    if len(ticker_list) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 100 tickers per bulk request.",
        )

    # PostgreSQL DISTINCT ON: latest row per ticker ordered by date DESC.
    stmt = (
        select(NewsSentimentDaily)
        .where(NewsSentimentDaily.ticker.in_(ticker_list))
        .distinct(NewsSentimentDaily.ticker)
        .order_by(NewsSentimentDaily.ticker, NewsSentimentDaily.date.desc())
    )

    try:
        result = await session.execute(stmt)
        rows = result.scalars().all()
    except Exception:
        logger.exception("Failed to fetch bulk sentiment for tickers=%s", ticker_list)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve sentiment data.",
        )

    return BulkSentimentResponse(tickers=[_row_to_daily(r) for r in rows])


@router.get(
    "/macro",
    response_model=MacroSentimentResponse,
    status_code=status.HTTP_200_OK,
    summary="Macro sentiment timeseries",
    description=(
        "Returns the aggregated macro-level sentiment timeseries. "
        "Macro rows are stored under the reserved ticker `__MACRO__`."
    ),
)
async def get_macro_sentiment(
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Number of calendar days to look back (default 30)"),
    ] = 30,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> MacroSentimentResponse:
    """Retrieve macro sentiment timeseries.

    Args:
        days: Look-back window in calendar days.
        current_user: Authenticated user (injected by dependency).
        session: Async SQLAlchemy session (injected by dependency).

    Returns:
        MacroSentimentResponse with sentiment rows ordered newest first.
    """
    since = datetime.now(timezone.utc).date() - timedelta(days=days)

    stmt = (
        select(NewsSentimentDaily)
        .where(
            NewsSentimentDaily.ticker == _MACRO_TICKER,
            NewsSentimentDaily.date >= since,
        )
        .order_by(NewsSentimentDaily.date.desc())
    )

    try:
        result = await session.execute(stmt)
        rows = result.scalars().all()
    except Exception:
        logger.exception("Failed to fetch macro sentiment days=%d", days)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve macro sentiment data.",
        )

    return MacroSentimentResponse(data=[_row_to_daily(r) for r in rows])


# ---------------------------------------------------------------------------
# Path-param routes below — after all literal routes.
# ---------------------------------------------------------------------------


@router.get(
    "/{ticker}",
    response_model=SentimentTimeseriesResponse,
    status_code=status.HTTP_200_OK,
    summary="Daily sentiment timeseries for a ticker",
    description=(
        "Returns the daily sentiment scores for a single ticker over the requested "
        "look-back window. Results are ordered newest first."
    ),
)
async def get_ticker_sentiment(
    ticker: str,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Number of calendar days to look back (default 30)"),
    ] = 30,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> SentimentTimeseriesResponse:
    """Retrieve sentiment timeseries for a single ticker.

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        days: Look-back window in calendar days.
        current_user: Authenticated user (injected by dependency).
        session: Async SQLAlchemy session (injected by dependency).

    Returns:
        SentimentTimeseriesResponse with sentiment rows ordered newest first.
    """
    ticker_upper = ticker.upper()
    since = datetime.now(timezone.utc).date() - timedelta(days=days)

    stmt = (
        select(NewsSentimentDaily)
        .where(
            NewsSentimentDaily.ticker == ticker_upper,
            NewsSentimentDaily.date >= since,
        )
        .order_by(NewsSentimentDaily.date.desc())
    )

    try:
        result = await session.execute(stmt)
        rows = result.scalars().all()
    except Exception:
        logger.exception("Failed to fetch sentiment for ticker=%s days=%d", ticker_upper, days)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve sentiment data.",
        )

    return SentimentTimeseriesResponse(
        ticker=ticker_upper,
        data=[_row_to_daily(r) for r in rows],
    )


@router.get(
    "/{ticker}/articles",
    response_model=ArticleListResponse,
    status_code=status.HTTP_200_OK,
    summary="Paginated articles for a ticker",
    description=(
        "Returns paginated news article metadata for the requested ticker. "
        "Full article text is not stored; only headline, source, and event type."
    ),
)
async def get_ticker_articles(
    ticker: str,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maximum number of articles to return (default 50)"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Pagination offset (default 0)"),
    ] = 0,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Number of calendar days to look back (default 30)"),
    ] = 30,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ArticleListResponse:
    """Retrieve paginated news articles for a single ticker.

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        limit: Maximum rows to return (1–200).
        offset: Number of rows to skip for pagination.
        days: Look-back window in calendar days.
        current_user: Authenticated user (injected by dependency).
        session: Async SQLAlchemy session (injected by dependency).

    Returns:
        ArticleListResponse with articles and total count for pagination.
    """
    ticker_upper = ticker.upper()
    since = datetime.now(timezone.utc).date() - timedelta(days=days)

    base_filter = [
        NewsArticle.ticker == ticker_upper,
        NewsArticle.published_at >= since,
    ]

    count_stmt = select(func.count()).select_from(NewsArticle).where(*base_filter)
    data_stmt = (
        select(NewsArticle)
        .where(*base_filter)
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
        .offset(offset)
    )

    try:
        total_result = await session.execute(count_stmt)
        total: int = total_result.scalar_one()

        data_result = await session.execute(data_stmt)
        articles = data_result.scalars().all()
    except Exception:
        logger.exception("Failed to fetch articles for ticker=%s days=%d", ticker_upper, days)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve article data.",
        )

    article_responses = [
        ArticleSummaryResponse(
            headline=a.headline,
            source=a.source,
            source_url=a.source_url,
            ticker=a.ticker,
            published_at=a.published_at.isoformat(),
            event_type=a.event_type,
            scored_at=a.scored_at.isoformat() if a.scored_at else None,
        )
        for a in articles
    ]

    return ArticleListResponse(
        ticker=ticker_upper,
        articles=article_responses,
        total=total,
        limit=limit,
        offset=offset,
    )
