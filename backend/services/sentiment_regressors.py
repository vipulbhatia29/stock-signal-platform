"""Sentiment regressor fetcher — Prophet-free helper for forecasting + backtest.

Lives outside ``backend.tools.forecasting`` so callers (notably
``backend.services.backtesting``) can import it without dragging the
Prophet module load chain along. The function itself only depends on
SQLAlchemy + pandas + the ``NewsSentimentDaily`` model.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.news_sentiment import NewsSentimentDaily

logger = logging.getLogger(__name__)


async def fetch_sentiment_regressors(
    ticker: str,
    start_date: date | datetime | pd.Timestamp,
    end_date: date | datetime | pd.Timestamp,
    db: AsyncSession,
) -> pd.DataFrame | None:
    """Fetch daily sentiment data as Prophet regressors for a date range.

    Bounded inclusive on both ends. Returns tz-naive timestamps so callers
    can match against tz-naive Prophet date columns without raising
    ``Cannot compare tz-naive and tz-aware`` at merge time.

    Args:
        ticker: Stock ticker symbol.
        start_date: Range start (date, datetime, or pandas Timestamp).
        end_date: Range end (date, datetime, or pandas Timestamp).
        db: Async database session.

    Returns:
        DataFrame with columns [ds, stock_sentiment, sector_sentiment,
        macro_sentiment], or None if no sentiment data exists for this
        ticker in the range.
    """
    start_d = start_date.date() if isinstance(start_date, (datetime, pd.Timestamp)) else start_date
    end_d = end_date.date() if isinstance(end_date, (datetime, pd.Timestamp)) else end_date

    result = await db.execute(
        select(
            NewsSentimentDaily.date,
            NewsSentimentDaily.stock_sentiment,
            NewsSentimentDaily.sector_sentiment,
            NewsSentimentDaily.macro_sentiment,
        ).where(
            NewsSentimentDaily.ticker == ticker,
            NewsSentimentDaily.date >= start_d,
            NewsSentimentDaily.date <= end_d,
        )
    )
    rows = result.all()
    if not rows:
        return None

    sentiment_cols = ["ds", "stock_sentiment", "sector_sentiment", "macro_sentiment"]
    # pd.Index() wrapper avoids the pandas-stub `list[str]` → `Axes` pyright gap.
    df = pd.DataFrame(rows, columns=pd.Index(sentiment_cols))
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    return df
