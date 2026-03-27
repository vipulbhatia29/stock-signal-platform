"""Search and ingest endpoints.

Search combines local DB results with Yahoo Finance external search.
Ingest delegates to the pipelines service for full ticker orchestration.
"""

from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.stock import Stock
from backend.models.user import User
from backend.schemas.stock import IngestResponse, StockSearchResponse
from backend.services.exceptions import IngestFailedError

logger = logging.getLogger(__name__)

TICKER_PATTERN = re.compile(r"^[A-Za-z0-9.\-]{1,10}$")

# Yahoo Finance search — allowed quote types (equities + ETFs)
_YF_ALLOWED_TYPES = {"EQUITY", "ETF"}

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Yahoo Finance external search
# ─────────────────────────────────────────────────────────────────────────────


async def _yahoo_search(query: str, limit: int = 8) -> list[StockSearchResponse]:
    """Search Yahoo Finance for stocks and ETFs by name or ticker.

    Returns results not yet in our database, so the frontend can offer
    an "Add" action. Only US-listed equities and ETFs are included.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params={
                    "q": query,
                    "quotesCount": limit,
                    "newsCount": 0,
                    "listsCount": 0,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; StockSignalPlatform/1.0)",
                },
            )
            resp.raise_for_status()
            quotes = resp.json().get("quotes", [])
    except Exception:
        logger.warning("yahoo_search_failed", extra={"query": query})
        return []

    results = []
    for q_item in quotes:
        if q_item.get("quoteType") not in _YF_ALLOWED_TYPES:
            continue
        # Yahoo uses "." for multi-class shares (BRK.B), yfinance uses "-"
        ticker = q_item.get("symbol", "").replace(".", "-")
        # Skip non-US listings
        exchange = q_item.get("exchDisp", "")
        if exchange not in {"NASDAQ", "NYSE", "NYSEArca", "NasdaqGS", "NasdaqGM", "NasdaqCM"}:
            continue
        results.append(
            StockSearchResponse(
                ticker=ticker,
                name=q_item.get("longname") or q_item.get("shortname", ""),
                exchange=exchange,
                sector=q_item.get("sectorDisp"),
                in_db=False,
            )
        )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Stock search
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/search", response_model=list[StockSearchResponse])
async def search_stocks(
    q: str = Query(
        min_length=1, max_length=20, description="Search query (ticker or company name)"
    ),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[StockSearchResponse]:
    """Search stocks by ticker symbol or company name.

    First searches the local database (instant), then supplements with
    Yahoo Finance results for stocks not yet in the DB. External results
    have ``in_db=False`` so the frontend can show an "Add" action.
    """
    limit = 10

    # 1. Local DB search (fast)
    db_query = (
        select(Stock)
        .where((Stock.ticker.ilike(f"{q}%")) | (Stock.name.ilike(f"%{q}%")))
        .where(Stock.is_active.is_(True))
        .order_by(Stock.ticker)
        .limit(limit)
    )
    result = await db.execute(db_query)
    db_stocks = list(result.scalars().all())

    db_results = [
        StockSearchResponse(
            ticker=s.ticker,
            name=s.name,
            exchange=s.exchange,
            sector=s.sector,
            in_db=True,
        )
        for s in db_stocks
    ]

    # 2. If DB has enough results, skip external search
    if len(db_results) >= limit:
        return db_results

    # 3. Supplement with Yahoo Finance (only for stocks not in DB)
    db_tickers = {r.ticker for r in db_results}
    external = await _yahoo_search(q, limit=limit - len(db_results))
    external_filtered = [r for r in external if r.ticker not in db_tickers]

    return db_results + external_filtered[: limit - len(db_results)]


# ─────────────────────────────────────────────────────────────────────────────
# On-demand data ingestion
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{ticker}/ingest", response_model=IngestResponse)
async def ingest_ticker(
    ticker: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> IngestResponse:
    """Ingest price data and compute signals for a ticker.

    If the ticker has no data, fetches 10Y of history. If it already has
    data, performs a delta fetch (only new data since the last stored row).
    After fetching, computes technical signals and stores a snapshot.

    Returns 201 for newly ingested tickers, 200 for delta updates.
    """
    ticker = ticker.upper().strip()
    if not TICKER_PATTERN.match(ticker):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ticker format. Use alphanumeric characters, dots, and hyphens only.",
        )

    from backend.services.pipelines import ingest_ticker as ingest_ticker_svc

    try:
        result = await ingest_ticker_svc(
            ticker=ticker,
            db=db,
            user_id=str(current_user.id),
        )
    except IngestFailedError as exc:
        logger.error("Ingest failed for %s at step %s", exc.ticker, exc.step)
        if exc.step == "ensure_stock_exists":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock not found",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Failed to fetch price data",
        )

    cache = getattr(request.app.state, "cache", None)
    if cache:
        await cache.invalidate_ticker(ticker)

    return IngestResponse(
        ticker=result["ticker"],
        name=result["stock_name"],
        rows_fetched=result["rows_fetched"],
        composite_score=result["composite_score"],
        status="created" if result["is_new"] else "updated",
    )
