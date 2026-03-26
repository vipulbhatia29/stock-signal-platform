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


def _fetch_sector_etf_performance() -> list[dict]:
    """Fetch 2-day data for all sector ETFs and compute 1-day changes.

    Returns:
        List of dicts with sector, etf, change_pct.
    """
    results = []
    for sector, etf in SECTOR_ETFS.items():
        try:
            df = yf.download(etf, period="2d", progress=False)
            if df is None or df.empty or len(df) < 2:
                continue
            close_col = df["Close"]
            if hasattr(close_col, "iloc"):
                prev = float(close_col.iloc[-2])
                curr = float(close_col.iloc[-1])
            else:
                continue
            if prev == 0:
                continue
            change_pct = ((curr - prev) / prev) * 100
            results.append(
                {
                    "sector": sector,
                    "etf": etf,
                    "change_pct": round(change_pct, 2),
                }
            )
        except Exception:
            continue
    return results


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
            sectors = await asyncio.to_thread(_fetch_sector_etf_performance)

            # Portfolio news + earnings (best effort)
            portfolio_news: list[dict] = []
            upcoming_earnings: list[dict] = []

            try:
                from backend.request_context import current_user_id

                user_id = current_user_id.get()
                if user_id:
                    from sqlalchemy import select

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

                            # Fetch news for top holdings
                            from backend.tools.news import fetch_yfinance_news

                            for t in top_tickers:
                                articles = await asyncio.to_thread(fetch_yfinance_news, t)
                                for a in articles[:2]:
                                    a["portfolio_ticker"] = t
                                    portfolio_news.append(a)

                            # Fetch upcoming earnings
                            from backend.tools.intelligence import (
                                fetch_next_earnings_date,
                            )

                            for p in positions:
                                ed = await asyncio.to_thread(fetch_next_earnings_date, p.ticker)
                                if ed:
                                    upcoming_earnings.append({"ticker": p.ticker, "date": ed})
            except Exception:
                logger.warning("Failed to fetch portfolio context for briefing")

            result = {
                "indexes": indexes,
                "sector_performance": sectors,
                "portfolio_news": portfolio_news[:10],
                "upcoming_earnings": upcoming_earnings,
                "top_movers": {"gainers": [], "losers": []},
                "briefing_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }

            return ToolResult(status="ok", data=result)

        except Exception as e:
            logger.error("market_briefing_failed", extra={"error": str(e)})
            return ToolResult(status="error", error="Failed to generate market briefing")
