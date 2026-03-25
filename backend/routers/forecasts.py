"""Forecast and scorecard API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.forecast import ForecastResult, ModelVersion
from backend.models.portfolio import Portfolio, Position
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.models.user import User
from backend.schemas.forecasts import (
    ForecastHorizon,
    ForecastResponse,
    HorizonBreakdownResponse,
    PortfolioForecastHorizon,
    PortfolioForecastResponse,
    ScorecardResponse,
    SectorForecastResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["forecasts"])

# Sector-to-ETF mapping
SECTOR_ETF_MAP: dict[str, str] = {
    "technology": "XLK",
    "healthcare": "XLV",
    "financials": "XLF",
    "consumer discretionary": "XLY",
    "consumer staples": "XLP",
    "energy": "XLE",
    "industrials": "XLI",
    "materials": "XLB",
    "utilities": "XLU",
    "real estate": "XLRE",
    "communication services": "XLC",
}


@router.get(
    "/forecasts/portfolio",
    response_model=PortfolioForecastResponse,
    summary="Get aggregated portfolio forecast",
)
async def get_portfolio_forecast(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PortfolioForecastResponse:
    """Compute portfolio-level forecast using weighted aggregation.

    Args:
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        PortfolioForecastResponse with aggregated horizons.
    """
    # Get user's portfolio positions
    port_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [r[0] for r in port_result.all()]

    if not portfolio_ids:
        return PortfolioForecastResponse(horizons=[], ticker_count=0)

    pos_result = await db.execute(
        select(Position).where(
            Position.portfolio_id.in_(portfolio_ids),
            Position.shares > 0,
        )
    )
    positions = pos_result.scalars().all()

    if not positions:
        return PortfolioForecastResponse(horizons=[], ticker_count=0)

    # Compute total value for weights
    total_value = 0.0
    position_values: dict[str, float] = {}

    for pos in positions:
        price_result = await db.execute(
            select(StockPrice.close)
            .where(StockPrice.ticker == pos.ticker)
            .order_by(StockPrice.time.desc())
            .limit(1)
        )
        price = price_result.scalar_one_or_none()
        if price:
            value = float(pos.shares) * float(price)
            position_values[pos.ticker] = value
            total_value += value

    if total_value == 0:
        return PortfolioForecastResponse(horizons=[], ticker_count=0)

    # Weighted forecast aggregation per horizon
    horizon_agg: dict[int, dict] = {}

    for ticker, value in position_values.items():
        weight = value / total_value

        latest_result = await db.execute(
            select(ForecastResult.forecast_date)
            .where(ForecastResult.ticker == ticker)
            .order_by(ForecastResult.forecast_date.desc())
            .limit(1)
        )
        latest_date = latest_result.scalar_one_or_none()
        if latest_date is None:
            continue

        fc_result = await db.execute(
            select(ForecastResult).where(
                ForecastResult.ticker == ticker,
                ForecastResult.forecast_date == latest_date,
            )
        )
        forecasts = fc_result.scalars().all()

        # Get current price for return calculation
        price_result = await db.execute(
            select(StockPrice.close)
            .where(StockPrice.ticker == ticker)
            .order_by(StockPrice.time.desc())
            .limit(1)
        )
        current_price = price_result.scalar_one_or_none()
        if not current_price:
            continue

        for fc in forecasts:
            if fc.horizon_days not in horizon_agg:
                horizon_agg[fc.horizon_days] = {
                    "return_sum": 0.0,
                    "lower_sum": 0.0,
                    "upper_sum": 0.0,
                }
            expected_return = (fc.predicted_price - float(current_price)) / float(current_price)
            lower_return = (fc.predicted_lower - float(current_price)) / float(current_price)
            upper_return = (fc.predicted_upper - float(current_price)) / float(current_price)

            horizon_agg[fc.horizon_days]["return_sum"] += weight * expected_return
            horizon_agg[fc.horizon_days]["lower_sum"] += weight * lower_return
            horizon_agg[fc.horizon_days]["upper_sum"] += weight * upper_return

    horizons = [
        PortfolioForecastHorizon(
            horizon_days=h,
            expected_return_pct=round(agg["return_sum"] * 100, 2),
            lower_pct=round(agg["lower_sum"] * 100, 2),
            upper_pct=round(agg["upper_sum"] * 100, 2),
            diversification_ratio=round(1.0 / max(len(position_values), 1), 2),
            confidence_level="medium",
        )
        for h, agg in sorted(horizon_agg.items())
    ]

    return PortfolioForecastResponse(
        horizons=horizons,
        ticker_count=len(position_values),
    )


@router.get(
    "/forecasts/{ticker}",
    response_model=ForecastResponse,
    summary="Get forecast for a ticker",
)
async def get_ticker_forecast(
    ticker: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> ForecastResponse:
    """Get the latest forecast for a ticker at all horizons.

    Args:
        ticker: Stock ticker symbol.
        request: FastAPI request (used for cache access).
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        ForecastResponse with horizons, model MAPE, and status.
    """
    ticker = ticker.upper()
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:forecast:{ticker}"
    if cache:
        from backend.services.cache import CacheTier

        cached = await cache.get(cache_key)
        if cached:
            return ForecastResponse.model_validate_json(cached)

    # Get latest forecast date for this ticker
    latest_date_result = await db.execute(
        select(ForecastResult.forecast_date)
        .where(ForecastResult.ticker == ticker)
        .order_by(ForecastResult.forecast_date.desc())
        .limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()

    if latest_date is None:
        raise HTTPException(status_code=404, detail="No forecast available for this ticker")

    # Get all horizons for that date
    result = await db.execute(
        select(ForecastResult).where(
            ForecastResult.ticker == ticker,
            ForecastResult.forecast_date == latest_date,
        )
    )
    forecasts = result.scalars().all()

    # Get model info
    model_result = await db.execute(
        select(ModelVersion).where(
            ModelVersion.ticker == ticker,
            ModelVersion.is_active.is_(True),
        )
    )
    model = model_result.scalar_one_or_none()

    # Get Sharpe direction
    from backend.tools.forecasting import compute_sharpe_direction

    sharpe_dir = await compute_sharpe_direction(ticker, db)

    horizons = []
    for fc in forecasts:
        mape = (model.metrics or {}).get("rolling_mape") if model else None
        confidence = _mape_to_confidence(mape)
        horizons.append(
            ForecastHorizon(
                horizon_days=fc.horizon_days,
                predicted_price=fc.predicted_price,
                predicted_lower=fc.predicted_lower,
                predicted_upper=fc.predicted_upper,
                target_date=fc.target_date,
                confidence_level=confidence,
                sharpe_direction=sharpe_dir,
            )
        )

    horizons.sort(key=lambda h: h.horizon_days)

    response = ForecastResponse(
        ticker=ticker,
        horizons=horizons,
        model_mape=(model.metrics or {}).get("rolling_mape") if model else None,
        model_status=model.status if model else "none",
    )
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), tier=CacheTier.STANDARD)
    return response


@router.get(
    "/forecasts/sector/{sector}",
    response_model=SectorForecastResponse,
    summary="Get forecast for a sector via ETF proxy",
)
async def get_sector_forecast(
    sector: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> SectorForecastResponse:
    """Get forecast for a sector using its ETF proxy ticker.

    Args:
        sector: Sector name (case-insensitive).
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        SectorForecastResponse with ETF forecast and user exposure.
    """
    etf_ticker = SECTOR_ETF_MAP.get(sector.lower())
    if etf_ticker is None:
        raise HTTPException(status_code=404, detail=f"Unknown sector: {sector}")

    # Get ETF forecast
    latest_result = await db.execute(
        select(ForecastResult.forecast_date)
        .where(ForecastResult.ticker == etf_ticker)
        .order_by(ForecastResult.forecast_date.desc())
        .limit(1)
    )
    latest_date = latest_result.scalar_one_or_none()

    horizons: list[ForecastHorizon] = []
    if latest_date:
        fc_result = await db.execute(
            select(ForecastResult).where(
                ForecastResult.ticker == etf_ticker,
                ForecastResult.forecast_date == latest_date,
            )
        )
        forecasts = fc_result.scalars().all()

        for fc in forecasts:
            horizons.append(
                ForecastHorizon(
                    horizon_days=fc.horizon_days,
                    predicted_price=fc.predicted_price,
                    predicted_lower=fc.predicted_lower,
                    predicted_upper=fc.predicted_upper,
                    target_date=fc.target_date,
                )
            )
        horizons.sort(key=lambda h: h.horizon_days)

    # Compute user exposure to this sector
    user_tickers: list[str] = []
    port_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [r[0] for r in port_result.all()]

    if portfolio_ids:
        pos_result = await db.execute(
            select(Position.ticker)
            .where(
                Position.portfolio_id.in_(portfolio_ids),
                Position.shares > 0,
            )
            .distinct()
        )
        held_tickers = [r[0] for r in pos_result.all()]

        # Check which held tickers are in this sector
        if held_tickers:
            sector_result = await db.execute(
                select(Stock.ticker).where(
                    Stock.ticker.in_(held_tickers),
                    Stock.sector.ilike(f"%{sector}%"),
                )
            )
            user_tickers = [r[0] for r in sector_result.all()]

    return SectorForecastResponse(
        sector=sector.title(),
        etf_ticker=etf_ticker,
        horizons=horizons,
        user_tickers_in_sector=user_tickers,
    )


@router.get(
    "/recommendations/scorecard",
    response_model=ScorecardResponse,
    summary="Get recommendation performance scorecard",
)
async def get_scorecard(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> ScorecardResponse:
    """Get the user's recommendation accuracy scorecard.

    Args:
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        ScorecardResponse with hit rates, alpha, and horizon breakdowns.
    """
    from backend.tools.scorecard import compute_scorecard

    scorecard = await compute_scorecard(current_user.id, db)

    return ScorecardResponse(
        total_outcomes=scorecard.total_outcomes,
        overall_hit_rate=round(scorecard.overall_hit_rate, 4),
        avg_alpha=round(scorecard.avg_alpha, 4),
        buy_hit_rate=round(scorecard.buy_hit_rate, 4),
        sell_hit_rate=round(scorecard.sell_hit_rate, 4),
        worst_miss_pct=scorecard.worst_miss_pct,
        worst_miss_ticker=scorecard.worst_miss_ticker,
        by_horizon=[
            HorizonBreakdownResponse(
                horizon_days=h.horizon_days,
                total=h.total,
                correct=h.correct,
                hit_rate=round(h.hit_rate, 4),
                avg_alpha=round(h.avg_alpha, 4),
            )
            for h in scorecard.horizons
        ],
    )


def _mape_to_confidence(mape: float | None) -> str:
    """Convert MAPE to a confidence level string.

    Args:
        mape: Mean Absolute Percentage Error.

    Returns:
        "high", "medium", or "low".
    """
    if mape is None:
        return "medium"
    if mape < 0.10:
        return "high"
    if mape < 0.20:
        return "medium"
    return "low"
