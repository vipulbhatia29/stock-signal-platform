"""Stock intelligence fetch functions — upgrades, insider, earnings, EPS revisions.

All functions are synchronous (yfinance). Run in thread pool via asyncio.to_thread().
Caller is responsible for caching.
"""

from __future__ import annotations

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_upgrades_downgrades(ticker: str, max_results: int = 20) -> list[dict]:
    """Fetch recent analyst rating changes from yfinance.

    Returns:
        List of dicts with firm, to_grade, from_grade, action, date.
    """
    try:
        t = yf.Ticker(ticker.upper())
        df = t.upgrades_downgrades
        if df is None or df.empty:
            return []
        results = []
        for date, row in df.head(max_results).iterrows():
            results.append(
                {
                    "firm": row.get("Firm", ""),
                    "to_grade": row.get("ToGrade", ""),
                    "from_grade": row.get("FromGrade", ""),
                    "action": row.get("Action", ""),
                    "date": str(date.date()) if hasattr(date, "date") else str(date),
                }
            )
        return results
    except Exception:
        logger.warning("Failed to fetch upgrades for %s", ticker)
        return []


def fetch_insider_transactions(ticker: str, max_results: int = 10) -> list[dict]:
    """Fetch recent insider transactions from yfinance.

    Returns:
        List of dicts with insider_name, relation, transaction_type, shares, value, date.
    """
    try:
        t = yf.Ticker(ticker.upper())
        df = t.insider_transactions
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.head(max_results).iterrows():
            results.append(
                {
                    "insider_name": row.get("Insider Trading", row.get("Name", "")),
                    "relation": row.get("Relationship", row.get("Relation", "")),
                    "transaction_type": row.get("Transaction", ""),
                    "shares": int(row.get("Shares", 0)),
                    "value": float(row.get("Value", 0)) if row.get("Value") else None,
                    "date": str(row.get("Start Date", row.get("Date", ""))),
                }
            )
        return results
    except Exception:
        logger.warning("Failed to fetch insider transactions for %s", ticker)
        return []


def fetch_next_earnings_date(ticker: str) -> str | None:
    """Fetch next earnings date from yfinance calendar.

    Returns:
        ISO date string or None.
    """
    try:
        t = yf.Ticker(ticker.upper())
        cal = t.calendar
        if cal is None:
            return None
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if dates:
                return str(dates[0].date()) if hasattr(dates[0], "date") else str(dates[0])
        return None
    except Exception:
        logger.warning("Failed to fetch calendar for %s", ticker)
        return None


def fetch_eps_revisions(ticker: str) -> dict | None:
    """Fetch EPS revision data from yfinance.

    Returns:
        Dict with revision data or None.
    """
    try:
        t = yf.Ticker(ticker.upper())
        rev = t.eps_revisions
        if rev is None or (hasattr(rev, "empty") and rev.empty):
            return None
        if hasattr(rev, "to_dict"):
            return rev.to_dict()
        return None
    except Exception:
        logger.warning("Failed to fetch EPS revisions for %s", ticker)
        return None


def fetch_short_interest(ticker: str) -> dict | None:
    """Fetch short interest data from yfinance.

    Returns:
        Dict with short_percent_of_float, short_ratio, shares_short,
        or None if unavailable.
    """
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info or {}
        short_pct = info.get("shortPercentOfFloat")
        if short_pct is None:
            return None
        return {
            "short_percent_of_float": round(float(short_pct) * 100, 2),
            "short_ratio": info.get("shortRatio"),
            "shares_short": info.get("sharesShort"),
        }
    except Exception:
        logger.warning("Failed to fetch short interest for %s", ticker)
        return None
