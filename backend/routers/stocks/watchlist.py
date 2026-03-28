"""Watchlist management endpoints — CRUD + refresh.

Delegates business logic to ``backend.services.watchlist``. Translates
service exceptions into HTTP responses.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.rate_limit import limiter
from backend.schemas.stock import WatchlistAddRequest, WatchlistItemResponse
from backend.services.exceptions import DuplicateWatchlistError, StockNotFoundError
from backend.services.watchlist import (
    acknowledge_price,
    get_watchlist_tickers,
)
from backend.services.watchlist import (
    add_to_watchlist as add_to_watchlist_svc,
)
from backend.services.watchlist import (
    get_watchlist as get_watchlist_svc,
)
from backend.services.watchlist import (
    remove_from_watchlist as remove_from_watchlist_svc,
)
from backend.tasks.market_data import refresh_ticker_task
from backend.validation import TickerPath

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_WATCHLIST_SIZE = 100


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
    return await get_watchlist_svc(current_user.id, db)


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
    try:
        return await add_to_watchlist_svc(current_user.id, body.ticker, db)
    except StockNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock '{body.ticker.upper()}' not found. "
            "Make sure the ticker is correct and has been added to the system.",
        )
    except DuplicateWatchlistError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{body.ticker.upper()}' is already in your watchlist.",
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Watchlist is full (maximum {MAX_WATCHLIST_SIZE} tickers). "
            "Remove a ticker before adding a new one.",
        )


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    ticker: TickerPath,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove a stock from the user's watchlist.

    Returns 204 No Content on success (standard REST pattern for DELETE).
    Returns 404 if the ticker isn't in the user's watchlist.
    """
    try:
        await remove_from_watchlist_svc(current_user.id, ticker, db)
    except StockNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{ticker.upper()}' is not in your watchlist.",
        )


@router.post("/watchlist/{ticker}/acknowledge", response_model=WatchlistItemResponse)
async def acknowledge_watchlist_price(
    ticker: TickerPath,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Acknowledge stale price data for a watchlist entry.

    Sets price_acknowledged_at to now, clearing the stale-data amber
    indicator in the UI until a newer price arrives.
    Returns 404 if the ticker is not in the user's watchlist.
    """
    try:
        return await acknowledge_price(current_user.id, ticker, db)
    except StockNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{ticker.upper()}' is not in your watchlist.",
        )


@router.post("/watchlist/refresh-all")
@limiter.limit("2/minute")
async def refresh_all_watchlist(
    request: Request,  # required by slowapi for rate limiting
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Enqueue background refresh tasks for all tickers in user's watchlist.

    Each ticker gets a Celery task to fetch latest prices and recompute signals.
    Returns a list of {ticker, task_id} for the frontend to poll task status.
    Rate limited to 2 requests/minute (expensive yfinance operation).
    """
    tickers = await get_watchlist_tickers(current_user.id, db)

    tasks = []
    for ticker in tickers:
        task = refresh_ticker_task.delay(ticker)
        tasks.append({"ticker": ticker, "task_id": task.id})
        logger.info("Enqueued refresh for %s — task_id=%s", ticker, task.id)

    return tasks
