"""DividendSustainabilityTool — on-demand yfinance dividend health check."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class DividendSustainabilityInput(BaseModel):
    """Input schema for dividend_sustainability tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


class DividendSustainabilityTool(BaseTool):
    """Assess dividend sustainability for a stock.

    Fetches payout ratio, free cash flow, dividend rate/yield from
    yfinance on-demand. Classifies sustainability as safe/moderate/at_risk.
    """

    name = "dividend_sustainability"
    description = (
        "Assess dividend sustainability: payout ratio, free cash flow "
        "coverage, dividend rate, yield, and sustainability rating "
        "(safe/moderate/at_risk). Fetches live data from yfinance."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol",
            },
        },
        "required": ["ticker"],
    }
    args_schema: ClassVar[type[BaseModel] | None] = DividendSustainabilityInput
    timeout_seconds = 15.0

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        """Fetch dividend metrics and assess sustainability."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        # yfinance is synchronous — run in executor
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            info = await loop.run_in_executor(pool, self._fetch_dividend_info, ticker)

        if info is None:
            return ToolResult(
                status="error",
                error=f"Could not fetch data for '{ticker}'.",
            )

        return ToolResult(status="ok", data=info)

    @staticmethod
    def _fetch_dividend_info(ticker: str) -> dict[str, Any] | None:
        """Fetch dividend info from yfinance (synchronous)."""
        import yfinance as yf

        stock = yf.Ticker(ticker)
        info = stock.info or {}

        dividend_rate = info.get("dividendRate")
        dividend_yield = info.get("dividendYield")

        # Non-dividend payer
        if not dividend_rate and not dividend_yield:
            return {
                "ticker": ticker,
                "pays_dividend": False,
                "message": f"{ticker} does not currently pay a dividend.",
            }

        payout_ratio = info.get("payoutRatio")
        free_cashflow = info.get("freeCashflow")
        trailing_eps = info.get("trailingEps")
        market_cap = info.get("marketCap")

        # FCF coverage: how many times FCF covers total dividends
        fcf_coverage = None
        if free_cashflow and dividend_rate and market_cap and dividend_yield:
            # Total annual dividends ≈ market_cap * dividend_yield
            total_dividends = market_cap * dividend_yield
            if total_dividends > 0:
                fcf_coverage = round(free_cashflow / total_dividends, 2)

        # Sustainability classification
        sustainability = _classify_sustainability(payout_ratio, fcf_coverage)

        return {
            "ticker": ticker,
            "pays_dividend": True,
            "dividend_rate": dividend_rate,
            "dividend_yield": (round(dividend_yield * 100, 2) if dividend_yield else None),
            "payout_ratio": (round(payout_ratio * 100, 1) if payout_ratio else None),
            "free_cashflow": free_cashflow,
            "fcf_coverage": fcf_coverage,
            "trailing_eps": trailing_eps,
            "sustainability": sustainability,
        }


def _classify_sustainability(
    payout_ratio: float | None,
    fcf_coverage: float | None,
) -> str:
    """Classify dividend sustainability as safe/moderate/at_risk.

    Args:
        payout_ratio: Fraction of earnings paid as dividends (0-1+).
        fcf_coverage: How many times FCF covers dividends.

    Returns:
        One of "safe", "moderate", "at_risk", or "unknown".
    """
    if payout_ratio is None and fcf_coverage is None:
        return "unknown"

    risk_signals = 0

    if payout_ratio is not None:
        if payout_ratio > 1.0:
            risk_signals += 2  # Paying more than earnings
        elif payout_ratio > 0.75:
            risk_signals += 1  # High payout

    if fcf_coverage is not None:
        if fcf_coverage < 1.0:
            risk_signals += 2  # FCF doesn't cover dividends
        elif fcf_coverage < 1.5:
            risk_signals += 1  # Tight coverage

    if risk_signals >= 3:
        return "at_risk"
    elif risk_signals >= 1:
        return "moderate"
    return "safe"
