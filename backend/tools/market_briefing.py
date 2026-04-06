"""Market briefing tool — daily market overview for the agent.

Fetches index performance, sector ETFs, portfolio news, upcoming earnings,
and top movers. All yfinance calls are synchronous and run via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import yfinance as yf
from pydantic import BaseModel
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# ── Index and sector config ──────────────────────────────────────────────────

INDEXES = [
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow Jones"),
    ("^IXIC", "NASDAQ"),
    ("^VIX", "VIX"),
]

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


# ── Fetch functions ──────────────────────────────────────────────────────────


def _fetch_index_performance(ticker: str, name: str) -> dict | None:
    """Fetch 2-day price data for a single index and compute 1-day change.

    Args:
        ticker: Index ticker symbol.
        name: Human-readable index name.

    Returns:
        Dict with name, ticker, price, change_pct, or None on failure.
    """
    try:
        df = yf.download(ticker, period="2d", progress=False)
        if df is None or df.empty or len(df) < 2:
            return None
        close_col = df["Close"]
        if hasattr(close_col, "iloc"):
            prev = float(close_col.iloc[-2])
            curr = float(close_col.iloc[-1])
        else:
            return None
        if prev == 0:
            return None
        change_pct = ((curr - prev) / prev) * 100
        return {
            "name": name,
            "ticker": ticker,
            "price": round(curr, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception:
        logger.warning("Failed to fetch index %s", ticker)
        return None


async def _fetch_top_movers(db: AsyncSession, limit: int = 4) -> dict[str, list[dict]]:
    """Fetch top gainers and losers from latest signal snapshots.

    Args:
        db: Async database session.
        limit: Number of gainers/losers to return.

    Returns:
        Dict with 'gainers' and 'losers' lists sorted by change_pct.
    """
    from backend.models.signal import SignalSnapshot

    latest_ts_q = select(func.max(SignalSnapshot.computed_at))
    latest_ts = (await db.execute(latest_ts_q)).scalar_one_or_none()
    if not latest_ts:
        return {"gainers": [], "losers": []}

    base_q = select(
        SignalSnapshot.ticker,
        SignalSnapshot.current_price,
        SignalSnapshot.change_pct,
        SignalSnapshot.macd_signal_label,
        SignalSnapshot.composite_score,
    ).where(
        SignalSnapshot.computed_at == latest_ts,
        SignalSnapshot.change_pct.isnot(None),
    )

    def _to_dict(row: Any) -> dict:
        return {
            "ticker": row.ticker,
            "current_price": row.current_price,
            "change_pct": round(row.change_pct, 2),
            "macd_signal_label": row.macd_signal_label,
            "composite_score": row.composite_score,
        }

    gainers_q = base_q.order_by(desc(SignalSnapshot.change_pct)).limit(limit)
    gainers = [_to_dict(r) for r in (await db.execute(gainers_q)).all()]

    losers_q = base_q.order_by(asc(SignalSnapshot.change_pct)).limit(limit)
    losers = [_to_dict(r) for r in (await db.execute(losers_q)).all()]

    return {"gainers": gainers, "losers": losers}


async def _fetch_sector_etf_performance() -> list[dict]:
    """Fetch sector ETF performance in parallel.

    Returns:
        List of dicts with sector (normalized), etf, change_pct.
    """
    from backend.utils.sectors import normalize_sector

    async def _fetch_one(sector: str, etf: str) -> dict | None:
        try:
            ticker = await asyncio.to_thread(yf.Ticker, etf)
            info = await asyncio.to_thread(lambda: ticker.fast_info)
            prev = getattr(info, "previous_close", None)
            curr = getattr(info, "last_price", None)
            if prev and curr and prev > 0:
                change = ((curr - prev) / prev) * 100
                return {
                    "sector": normalize_sector(sector),
                    "etf": etf,
                    "change_pct": round(change, 2),
                }
        except Exception:
            logger.warning("Failed to fetch ETF %s for sector %s", etf, sector)
        return None

    tasks = [_fetch_one(sector, etf) for sector, etf in SECTOR_ETFS.items()]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ── Agent tool ───────────────────────────────────────────────────────────────


class MarketBriefingInput(BaseModel):
    """Input schema for market briefing tool."""

    pass  # No parameters needed


class MarketBriefingTool(BaseTool):
    """Get today's market briefing — indexes, sectors, portfolio news, earnings.

    Provides a comprehensive daily market overview including major index
    performance, sector ETF changes, news for portfolio holdings,
    upcoming earnings dates, and top movers.
    """

    name = "market_briefing"
    description = (
        "Get today's market briefing with index performance (S&P 500, NASDAQ, Dow, VIX), "
        "sector ETF changes, news for portfolio holdings, upcoming earnings dates, "
        "and top portfolio movers. Use for daily market overview questions."
    )
    category = "market"
    parameters = {"type": "object", "properties": {}, "required": []}
    args_schema = MarketBriefingInput
    timeout_seconds = 30.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute market briefing data fetch."""
        try:
            # Fetch indexes in parallel threads
            index_tasks = [
                asyncio.to_thread(_fetch_index_performance, ticker, name)
                for ticker, name in INDEXES
            ]
            index_results = await asyncio.gather(*index_tasks)
            indexes = [r for r in index_results if r is not None]

            # Fetch sector ETFs
            sectors = await _fetch_sector_etf_performance()

            # Portfolio news + earnings (best effort)
            portfolio_news: list[dict] = []
            upcoming_earnings: list[dict] = []

            try:
                from backend.request_context import current_user_id

                user_id = current_user_id.get()
                if user_id:
                    from backend.database import async_session_factory
                    from backend.models.portfolio import Portfolio, Position

                    async with async_session_factory() as db:
                        portfolio = (
                            await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
                        ).scalar_one_or_none()
                        if portfolio:
                            positions = (
                                (
                                    await db.execute(
                                        select(Position)
                                        .where(Position.portfolio_id == portfolio.id)
                                        .where(Position.shares > 0)
                                        .order_by(Position.shares.desc())
                                        .limit(5)
                                    )
                                )
                                .scalars()
                                .all()
                            )
                            top_tickers = [p.ticker for p in positions[:3]]

                            # Fetch news for top holdings (parallel)
                            from backend.tools.news import fetch_yfinance_news

                            news_results = await asyncio.gather(
                                *[asyncio.to_thread(fetch_yfinance_news, t) for t in top_tickers],
                                return_exceptions=True,
                            )
                            for ticker, result in zip(top_tickers, news_results):
                                if isinstance(result, Exception):
                                    logger.warning(
                                        "news_fetch_failed",
                                        extra={"ticker": ticker, "error": str(result)},
                                    )
                                    continue
                                for a in result[:2]:
                                    a["portfolio_ticker"] = ticker
                                    portfolio_news.append(a)

                            # Fetch upcoming earnings (parallel)
                            from backend.tools.intelligence import (
                                fetch_next_earnings_date,
                            )

                            earnings_results = await asyncio.gather(
                                *[
                                    asyncio.to_thread(fetch_next_earnings_date, p.ticker)
                                    for p in positions
                                ],
                                return_exceptions=True,
                            )
                            for p, ed in zip(positions, earnings_results):
                                if isinstance(ed, Exception):
                                    logger.warning(
                                        "earnings_fetch_failed",
                                        extra={"ticker": p.ticker, "error": str(ed)},
                                    )
                                    continue
                                if ed:
                                    upcoming_earnings.append({"ticker": p.ticker, "date": ed})
            except Exception:
                logger.warning("Failed to fetch portfolio context for briefing")

            # Fetch general market news (best effort)
            general_news: list[dict] = []
            try:
                from backend.tools.news import fetch_google_news_rss

                raw_news = await fetch_google_news_rss("stock+market+today")
                general_news = [{**article, "portfolio_ticker": None} for article in raw_news[:3]]
            except Exception:
                logger.warning("Failed to fetch general market news")

            # Fetch top movers from signal snapshots
            top_movers: dict[str, list[dict]] = {"gainers": [], "losers": []}
            try:
                from backend.database import async_session_factory

                async with async_session_factory() as db:
                    top_movers = await _fetch_top_movers(db)
            except Exception:
                logger.warning("Failed to fetch top movers for briefing")

            result = {
                "indexes": indexes,
                "sector_performance": sectors,
                "portfolio_news": portfolio_news[:10],
                "general_news": general_news,
                "upcoming_earnings": upcoming_earnings,
                "top_movers": top_movers,
                "briefing_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }

            return ToolResult(status="ok", data=result)

        except Exception:
            logger.exception("Failed to generate market briefing")
            return ToolResult(status="error", error="Failed to generate market briefing")
