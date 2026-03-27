"""Forecast agent tools — read pre-computed forecasts from DB for agent use."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.constants import SECTOR_ETF_MAP
from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


# ── Input schemas ────────────────────────────────────────────


class ForecastInput(BaseModel):
    """Input schema for get_forecast tool."""

    ticker: str = Field(description="Stock ticker symbol (e.g., AAPL)")


class SectorForecastInput(BaseModel):
    """Input schema for get_sector_forecast tool."""

    sector: str = Field(description="GICS sector name (e.g., Technology, Healthcare)")


class PortfolioForecastInput(BaseModel):
    """Input schema for get_portfolio_forecast tool."""

    user_id: str = Field(description="User UUID (injected by executor)")


class CompareStocksInput(BaseModel):
    """Input schema for compare_stocks tool."""

    tickers: list[str] = Field(
        description="List of 2-5 ticker symbols to compare",
        min_length=2,
        max_length=5,
    )


# ── Tools ────────────────────────────────────────────────────


class GetForecastTool(BaseTool):
    """Get pre-computed Prophet forecast for a single stock.

    Returns predicted prices at 90/180/270 day horizons with confidence
    intervals, plus Sharpe direction trend.
    """

    name = "get_forecast"
    description = (
        "Get Prophet price forecast for a stock at 90/180/270 day horizons. "
        "Returns predicted price, confidence range, and Sharpe direction trend. "
        "Data is pre-computed nightly — no yfinance call at runtime."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol"},
        },
        "required": ["ticker"],
    }
    args_schema: ClassVar[type[BaseModel] | None] = ForecastInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["ticker"],
    )
    timeout_seconds = 5.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Read forecast from DB and enrich with Sharpe direction."""
        ticker = str(params.get("ticker", "")).upper().strip()
        if not ticker:
            return ToolResult(status="error", error="Missing required param: ticker")

        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.forecast import ForecastResult
            from backend.tools.forecasting import compute_sharpe_direction

            async with async_session_factory() as session:
                result = await session.execute(
                    select(ForecastResult)
                    .where(ForecastResult.ticker == ticker)
                    .order_by(
                        ForecastResult.forecast_date.desc(),
                        ForecastResult.horizon_days.asc(),
                    )
                    .limit(3)
                )
                forecasts = result.scalars().all()

                if not forecasts:
                    return ToolResult(
                        status="error",
                        error=(
                            f"No forecast data for '{ticker}'. "
                            "Run nightly pipeline or ingest first."
                        ),
                    )

                sharpe_direction = await compute_sharpe_direction(ticker, session)

            horizons = []
            for f in forecasts:
                horizons.append(
                    {
                        "horizon_days": f.horizon_days,
                        "target_date": f.target_date.isoformat(),
                        "predicted_price": f.predicted_price,
                        "predicted_lower": f.predicted_lower,
                        "predicted_upper": f.predicted_upper,
                        "confidence_range_pct": round(
                            (f.predicted_upper - f.predicted_lower) / f.predicted_price * 100, 1
                        ),
                    }
                )

            # Confidence level based on range width of shortest horizon
            first_range = horizons[0]["confidence_range_pct"] if horizons else 50.0
            if first_range < 15:
                confidence = "high"
            elif first_range < 30:
                confidence = "moderate"
            else:
                confidence = "low"

            return ToolResult(
                status="ok",
                data={
                    "ticker": ticker,
                    "forecast_date": forecasts[0].forecast_date.isoformat(),
                    "horizons": horizons,
                    "sharpe_direction": sharpe_direction,
                    "confidence": confidence,
                },
            )

        except Exception as e:
            logger.error("get_forecast_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=f"Failed to get forecast for {ticker}")


class GetSectorForecastTool(BaseTool):
    """Get forecast for a GICS sector via its ETF proxy.

    Maps sector name → ETF ticker (e.g., Technology → XLK), reads
    pre-computed forecast, and includes user's sector exposure.
    """

    name = "get_sector_forecast"
    description = (
        "Get Prophet forecast for a sector via its ETF proxy (e.g., Technology → XLK). "
        "Returns ETF forecast at 90/180/270d horizons plus user's "
        "portfolio exposure to that sector."
    )
    category = "data"
    parameters = {
        "type": "object",
        "properties": {
            "sector": {"type": "string", "description": "GICS sector name (e.g., Technology)"},
        },
        "required": ["sector"],
    }
    args_schema: ClassVar[type[BaseModel] | None] = SectorForecastInput
    cache_policy = CachePolicy(
        ttl=__import__("datetime").timedelta(hours=1),
        key_fields=["sector"],
    )
    timeout_seconds = 5.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Map sector to ETF and return forecast + exposure."""
        sector = str(params.get("sector", "")).strip()
        if not sector:
            return ToolResult(status="error", error="Missing required param: sector")

        etf_ticker = SECTOR_ETF_MAP.get(sector.lower())
        if not etf_ticker:
            available = ", ".join(sorted(SECTOR_ETF_MAP.keys()))
            return ToolResult(
                status="error",
                error=f"Unknown sector '{sector}'. Available: {available}",
            )

        try:
            from sqlalchemy import func, select

            from backend.database import async_session_factory
            from backend.models.forecast import ForecastResult
            from backend.models.stock import Stock

            async with async_session_factory() as session:
                # Get ETF forecast
                result = await session.execute(
                    select(ForecastResult)
                    .where(ForecastResult.ticker == etf_ticker)
                    .order_by(
                        ForecastResult.forecast_date.desc(),
                        ForecastResult.horizon_days.asc(),
                    )
                    .limit(3)
                )
                forecasts = result.scalars().all()

                # Count stocks in this sector that the user might hold
                sector_count_result = await session.execute(
                    select(func.count())
                    .select_from(Stock)
                    .where(func.lower(Stock.sector) == sector.lower())
                )
                sector_stock_count = sector_count_result.scalar() or 0

            if not forecasts:
                return ToolResult(
                    status="ok",
                    data={
                        "sector": sector,
                        "etf_ticker": etf_ticker,
                        "forecast_available": False,
                        "message": f"No forecast for {etf_ticker}. ETF may not be ingested yet.",
                        "tracked_stocks_in_sector": sector_stock_count,
                    },
                )

            horizons = []
            for f in forecasts:
                horizons.append(
                    {
                        "horizon_days": f.horizon_days,
                        "target_date": f.target_date.isoformat(),
                        "predicted_price": f.predicted_price,
                        "predicted_lower": f.predicted_lower,
                        "predicted_upper": f.predicted_upper,
                    }
                )

            return ToolResult(
                status="ok",
                data={
                    "sector": sector,
                    "etf_ticker": etf_ticker,
                    "forecast_available": True,
                    "forecast_date": forecasts[0].forecast_date.isoformat(),
                    "horizons": horizons,
                    "tracked_stocks_in_sector": sector_stock_count,
                },
            )

        except Exception as e:
            logger.error("get_sector_forecast_failed", extra={"sector": sector, "error": str(e)})
            return ToolResult(status="error", error=f"Failed to get sector forecast for {sector}")


class GetPortfolioForecastTool(BaseTool):
    """Get aggregate portfolio forecast based on individual stock forecasts.

    Computes weighted average predicted return across all held positions
    that have forecasts available.
    """

    name = "get_portfolio_forecast"
    description = (
        "Get aggregate portfolio forecast: weighted-average predicted returns "
        "across held positions with available forecasts. "
        "Includes per-stock contributions and confidence summary."
    )
    category = "portfolio"
    parameters = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User UUID (auto-injected)"},
        },
        "required": ["user_id"],
    }
    args_schema: ClassVar[type[BaseModel] | None] = PortfolioForecastInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Compute weighted portfolio forecast from individual stock forecasts."""
        import uuid as uuid_mod

        user_id_str = str(params.get("user_id", "")).strip()
        if not user_id_str:
            return ToolResult(status="error", error="Missing required param: user_id")

        try:
            user_id = uuid_mod.UUID(user_id_str)
        except ValueError:
            return ToolResult(status="error", error="Invalid user_id format")

        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.forecast import ForecastResult
            from backend.models.portfolio import Portfolio, Position

            async with async_session_factory() as session:
                # Get user's portfolio, then open positions
                portfolio_result = await session.execute(
                    select(Portfolio).where(Portfolio.user_id == user_id)
                )
                portfolio = portfolio_result.scalar_one_or_none()
                if not portfolio:
                    return ToolResult(
                        status="ok",
                        data={"message": "No portfolio found.", "holdings": 0},
                    )

                pos_result = await session.execute(
                    select(Position).where(
                        Position.portfolio_id == portfolio.id,
                        Position.shares > 0,
                    )
                )
                positions = pos_result.scalars().all()

                if not positions:
                    return ToolResult(
                        status="ok",
                        data={"message": "No open positions in portfolio.", "holdings": 0},
                    )

                # Compute total portfolio value
                total_value = sum(p.shares * (p.avg_cost_basis or 0) for p in positions)
                if total_value <= 0:
                    return ToolResult(
                        status="ok",
                        data={"message": "Portfolio value is zero.", "holdings": len(positions)},
                    )

                # Get latest forecasts for all held tickers
                held_tickers = [p.ticker for p in positions]
                fc_result = await session.execute(
                    select(ForecastResult)
                    .where(ForecastResult.ticker.in_(held_tickers))
                    .order_by(
                        ForecastResult.forecast_date.desc(),
                        ForecastResult.horizon_days.asc(),
                    )
                )
                all_forecasts = fc_result.scalars().all()

            # Group forecasts by ticker, keep only latest date per ticker
            forecast_by_ticker: dict[str, list[dict[str, Any]]] = {}
            seen_dates: dict[str, str] = {}
            for f in all_forecasts:
                fdate = f.forecast_date.isoformat()
                if f.ticker not in seen_dates:
                    seen_dates[f.ticker] = fdate
                if seen_dates[f.ticker] == fdate:
                    forecast_by_ticker.setdefault(f.ticker, []).append(
                        {
                            "horizon_days": f.horizon_days,
                            "predicted_price": f.predicted_price,
                            "predicted_lower": f.predicted_lower,
                            "predicted_upper": f.predicted_upper,
                        }
                    )

            # Weighted average per horizon
            position_map = {p.ticker: p for p in positions}
            horizon_agg: dict[int, dict[str, float]] = {}
            contributions = []

            for ticker, fc_list in forecast_by_ticker.items():
                pos = position_map.get(ticker)
                if not pos:
                    continue
                pos_value = pos.shares * (pos.avg_cost_basis or 0)
                weight = pos_value / total_value

                for fc in fc_list:
                    h = fc["horizon_days"]
                    # Predicted return from current cost basis
                    cost = pos.avg_cost_basis or 1
                    predicted_return = (fc["predicted_price"] - cost) / cost
                    agg = horizon_agg.setdefault(h, {"weighted_return": 0.0, "coverage_pct": 0.0})
                    agg["weighted_return"] += weight * predicted_return
                    agg["coverage_pct"] += weight * 100

                contributions.append(
                    {
                        "ticker": ticker,
                        "weight_pct": round(weight * 100, 1),
                        "horizons_available": len(fc_list),
                    }
                )

            horizon_results = []
            for h in sorted(horizon_agg.keys()):
                agg = horizon_agg[h]
                horizon_results.append(
                    {
                        "horizon_days": h,
                        "weighted_return_pct": round(agg["weighted_return"] * 100, 2),
                        "coverage_pct": round(agg["coverage_pct"], 1),
                    }
                )

            return ToolResult(
                status="ok",
                data={
                    "total_positions": len(positions),
                    "positions_with_forecast": len(forecast_by_ticker),
                    "total_value": round(total_value, 2),
                    "horizons": horizon_results,
                    "contributions": contributions,
                },
            )

        except Exception as e:
            logger.error("get_portfolio_forecast_failed", extra={"error": str(e)})
            return ToolResult(status="error", error="Failed to compute portfolio forecast")


class CompareStocksTool(BaseTool):
    """Compare 2-5 stocks side by side.

    Returns signals, fundamentals, and forecasts for each ticker
    in a structured format for easy comparison.
    """

    name = "compare_stocks"
    description = (
        "Compare 2-5 stocks side by side: signals, fundamentals (P/E, margins, "
        "growth), and forecasts. Returns structured comparison data."
    )
    category = "analysis"
    parameters = {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of 2-5 ticker symbols to compare",
                "minItems": 2,
                "maxItems": 5,
            },
        },
        "required": ["tickers"],
    }
    args_schema: ClassVar[type[BaseModel] | None] = CompareStocksInput
    timeout_seconds = 10.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Read signals, fundamentals, and forecasts for multiple tickers."""
        raw_tickers = params.get("tickers", [])
        if not raw_tickers or len(raw_tickers) < 2:
            return ToolResult(status="error", error="Provide at least 2 tickers to compare")
        if len(raw_tickers) > 5:
            return ToolResult(status="error", error="Maximum 5 tickers for comparison")

        tickers = [t.upper().strip() for t in raw_tickers]

        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.forecast import ForecastResult
            from backend.models.signal import SignalSnapshot
            from backend.models.stock import Stock

            async with async_session_factory() as session:
                # Stocks
                stock_result = await session.execute(select(Stock).where(Stock.ticker.in_(tickers)))
                stocks = {s.ticker: s for s in stock_result.scalars().all()}

                # Latest signals
                from sqlalchemy import func

                latest_signals_sub = (
                    select(
                        SignalSnapshot.ticker,
                        func.max(SignalSnapshot.computed_at).label("max_at"),
                    )
                    .where(SignalSnapshot.ticker.in_(tickers))
                    .group_by(SignalSnapshot.ticker)
                    .subquery()
                )
                signal_result = await session.execute(
                    select(SignalSnapshot).join(
                        latest_signals_sub,
                        (SignalSnapshot.ticker == latest_signals_sub.c.ticker)
                        & (SignalSnapshot.computed_at == latest_signals_sub.c.max_at),
                    )
                )
                signals = {s.ticker: s for s in signal_result.scalars().all()}

                # Latest forecasts
                fc_result = await session.execute(
                    select(ForecastResult)
                    .where(ForecastResult.ticker.in_(tickers))
                    .order_by(
                        ForecastResult.forecast_date.desc(),
                        ForecastResult.horizon_days.asc(),
                    )
                )
                all_fc = fc_result.scalars().all()

            # Group forecasts by ticker (latest date only)
            fc_by_ticker: dict[str, list[dict[str, Any]]] = {}
            seen_dates: dict[str, str] = {}
            for f in all_fc:
                fdate = f.forecast_date.isoformat()
                if f.ticker not in seen_dates:
                    seen_dates[f.ticker] = fdate
                if seen_dates[f.ticker] == fdate:
                    fc_by_ticker.setdefault(f.ticker, []).append(
                        {
                            "horizon_days": f.horizon_days,
                            "predicted_price": f.predicted_price,
                        }
                    )

            comparisons = []
            missing = []
            for t in tickers:
                stock = stocks.get(t)
                if not stock:
                    missing.append(t)
                    continue

                sig = signals.get(t)
                fc = fc_by_ticker.get(t, [])

                comparisons.append(
                    {
                        "ticker": t,
                        "name": stock.name,
                        "sector": stock.sector,
                        "market_cap": stock.market_cap,
                        "signals": {
                            "composite_score": sig.composite_score if sig else None,
                            "rsi": sig.rsi_14 if sig else None,
                            "recommendation": sig.recommendation if sig else None,
                        },
                        "fundamentals": {
                            "revenue_growth": stock.revenue_growth,
                            "gross_margins": stock.gross_margins,
                            "operating_margins": stock.operating_margins,
                            "profit_margins": stock.profit_margins,
                            "return_on_equity": stock.return_on_equity,
                        },
                        "forecast": fc if fc else None,
                    }
                )

            return ToolResult(
                status="ok",
                data={
                    "comparisons": comparisons,
                    "missing_tickers": missing,
                },
            )

        except Exception as e:
            logger.error("compare_stocks_failed", extra={"tickers": tickers, "error": str(e)})
            joined = ", ".join(tickers)
            return ToolResult(
                status="error",
                error=f"Failed to compare stocks: {joined}",
            )
