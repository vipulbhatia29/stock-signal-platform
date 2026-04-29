"""RiskNarrativeTool — structured risk summary with forecast context."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


class RiskNarrativeInput(BaseModel):
    """Input schema for risk_narrative tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


class RiskNarrativeTool(BaseTool):
    """Generate a structured risk narrative for a stock.

    Combines signals, fundamentals, forecast confidence, and sector
    context into a risk assessment with specific risk factors.
    """

    name = "risk_narrative"
    description = (
        "Generate a structured risk narrative for a stock. Combines "
        "signal strength, fundamental ratios, forecast confidence "
        "range, and sector ETF direction into actionable risk factors."
    )
    category = "analysis"
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
    args_schema: ClassVar[type[BaseModel] | None] = RiskNarrativeInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["ticker"],
    )
    timeout_seconds = 10.0

    async def _run(self, params: dict[str, Any]) -> ToolResult:
        """Build risk narrative from DB data."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        from sqlalchemy import select

        from backend.database import async_session_factory
        from backend.models.forecast import ForecastResult
        from backend.models.signal import SignalSnapshot
        from backend.models.stock import Stock

        # Step 1: fetch stock first — sector ETF lookup depends on stock.sector
        async with async_session_factory() as session:
            stock_result = await session.execute(select(Stock).where(Stock.ticker == ticker))
            stock = stock_result.scalar_one_or_none()

        if not stock:
            return ToolResult(
                status="error",
                error=(f"'{ticker}' not found. Use ingest_stock first."),
            )

        # Step 2: fetch signal, stock forecast, and sector ETF forecast in parallel
        # All three are independent reads with no data dependencies between them
        async def _fetch_signal() -> Any:
            async with async_session_factory() as session:
                sig_result = await session.execute(
                    select(SignalSnapshot)
                    .where(SignalSnapshot.ticker == ticker)
                    .order_by(SignalSnapshot.computed_at.desc())
                    .limit(1)
                )
                return sig_result.scalar_one_or_none()

        async def _fetch_forecast() -> Any:
            async with async_session_factory() as session:
                fc_result = await session.execute(
                    select(ForecastResult)
                    .where(
                        ForecastResult.ticker == ticker,
                        ForecastResult.horizon_days == 90,
                    )
                    .order_by(ForecastResult.forecast_date.desc())
                    .limit(1)
                )
                return fc_result.scalar_one_or_none()

        async def _fetch_sector_fc() -> Any:
            if not stock.sector:
                return None
            from backend.routers.forecasts import SECTOR_ETF_MAP

            etf = SECTOR_ETF_MAP.get(stock.sector.lower())
            if not etf:
                return None
            async with async_session_factory() as session:
                etf_result = await session.execute(
                    select(ForecastResult)
                    .where(
                        ForecastResult.ticker == etf,
                        ForecastResult.horizon_days == 90,
                    )
                    .order_by(ForecastResult.forecast_date.desc())
                    .limit(1)
                )
                return etf_result.scalar_one_or_none()

        signal, forecast, sector_fc = await asyncio.gather(
            _fetch_signal(),
            _fetch_forecast(),
            _fetch_sector_fc(),
        )

        # Build risk factors
        risk_factors = []
        risk_level = "moderate"

        # Signal-based risks
        if signal:
            if signal.composite_score is not None:
                if signal.composite_score < 3:
                    risk_factors.append(
                        {
                            "factor": "Weak composite score",
                            "detail": (f"Score {signal.composite_score:.1f}/10 — below threshold"),
                            "severity": "high",
                        }
                    )
                elif signal.composite_score < 5:
                    risk_factors.append(
                        {
                            "factor": "Below-average signal strength",
                            "detail": (f"Score {signal.composite_score:.1f}/10"),
                            "severity": "medium",
                        }
                    )

            if signal.rsi_14 is not None:
                if signal.rsi_14 > 70:
                    risk_factors.append(
                        {
                            "factor": "Overbought (RSI)",
                            "detail": f"RSI {signal.rsi_14:.0f} > 70",
                            "severity": "medium",
                        }
                    )
                elif signal.rsi_14 < 30:
                    risk_factors.append(
                        {
                            "factor": "Oversold (RSI)",
                            "detail": f"RSI {signal.rsi_14:.0f} < 30",
                            "severity": "low",
                        }
                    )

        # Fundamental risks
        if stock.return_on_equity is not None:
            if stock.return_on_equity < 0:
                risk_factors.append(
                    {
                        "factor": "Negative ROE",
                        "detail": (f"ROE {stock.return_on_equity:.1%} — unprofitable"),
                        "severity": "high",
                    }
                )

        if stock.revenue_growth is not None:
            if stock.revenue_growth < -0.1:
                risk_factors.append(
                    {
                        "factor": "Revenue declining",
                        "detail": (f"Revenue growth {stock.revenue_growth:.1%}"),
                        "severity": "high",
                    }
                )

        # Forecast-based risks
        forecast_context = None
        if forecast:
            spread_pct = (
                (forecast.return_upper_pct - forecast.return_lower_pct)
                / max(abs(forecast.expected_return_pct), 0.01)
                * 100
            )
            forecast_context = {
                "expected_return_pct": forecast.expected_return_pct,
                "confidence_range_pct": round(spread_pct, 1),
                "target_date": forecast.target_date.isoformat(),
            }
            if spread_pct > 30:
                risk_factors.append(
                    {
                        "factor": "Wide forecast confidence interval",
                        "detail": (f"90d range ±{spread_pct:.0f}% — high uncertainty"),
                        "severity": "medium",
                    }
                )

        # Sector context
        sector_context = None
        if sector_fc:
            sector_context = {
                "etf_ticker": sector_fc.ticker,
                "expected_return_pct": sector_fc.expected_return_pct,
                "target_date": sector_fc.target_date.isoformat(),
            }

        # Determine overall risk level
        high_count = sum(1 for f in risk_factors if f["severity"] == "high")
        if high_count >= 2:
            risk_level = "high"
        elif high_count == 1 or len(risk_factors) >= 3:
            risk_level = "elevated"
        elif len(risk_factors) == 0:
            risk_level = "low"

        return ToolResult(
            status="ok",
            data={
                "ticker": ticker,
                "name": stock.name,
                "sector": stock.sector,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "forecast_context": forecast_context,
                "sector_context": sector_context,
            },
        )
