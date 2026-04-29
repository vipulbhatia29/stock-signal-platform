"""Forecast and scorecard API endpoints."""

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import SECTOR_ETF_MAP
from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.forecast import ForecastResult, ModelVersion
from backend.models.portfolio import Portfolio, Position
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.models.user import User
from backend.schemas.forecasts import (
    ForecastDriver,
    ForecastEvaluation,
    ForecastHorizon,
    ForecastResponse,
    ForecastTrackRecordResponse,
    ForecastTrackRecordSummary,
    HorizonBreakdownResponse,
    ModelAccuracy,
    PortfolioForecastHorizon,
    PortfolioForecastResponse,
    ScorecardResponse,
    SectorForecastResponse,
)
from backend.validation import TickerPath

logger = logging.getLogger(__name__)

router = APIRouter(tags=["forecasts"])


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

    tickers = [pos.ticker for pos in positions]

    # Batch fetch latest prices for all position tickers (DISTINCT ON is PostgreSQL-specific)
    price_query = await db.execute(
        select(StockPrice.ticker, StockPrice.close)
        .distinct(StockPrice.ticker)
        .where(StockPrice.ticker.in_(tickers))
        .order_by(StockPrice.ticker, StockPrice.time.desc())
    )
    price_map: dict[str, float] = {row.ticker: float(row.close) for row in price_query}

    # Compute total value for weights using batch-fetched prices
    total_value = 0.0
    position_values: dict[str, float] = {}

    for pos in positions:
        price = price_map.get(pos.ticker)
        if price:
            value = float(pos.shares) * price
            position_values[pos.ticker] = value
            total_value += value

    if total_value == 0:
        return PortfolioForecastResponse(horizons=[], ticker_count=0)

    # Batch fetch latest forecast dates per ticker
    latest_dates_subq = (
        select(
            ForecastResult.ticker,
            func.max(ForecastResult.forecast_date).label("latest_date"),
        )
        .where(ForecastResult.ticker.in_(list(position_values.keys())))
        .group_by(ForecastResult.ticker)
        .subquery()
    )

    # Batch fetch all forecast results for latest dates
    fc_query = await db.execute(
        select(ForecastResult).join(
            latest_dates_subq,
            (ForecastResult.ticker == latest_dates_subq.c.ticker)
            & (ForecastResult.forecast_date == latest_dates_subq.c.latest_date),
        )
    )
    forecasts_by_ticker: dict[str, list[ForecastResult]] = defaultdict(list)
    for fc in fc_query.scalars().all():
        forecasts_by_ticker[fc.ticker].append(fc)

    # Track tickers without forecasts (KAN-404)
    tickers_with_forecast = set(forecasts_by_ticker.keys())
    missing_tickers = sorted(set(position_values.keys()) - tickers_with_forecast)

    # Recompute total using only tickers with forecasts
    forecast_value = sum(v for t, v in position_values.items() if t in tickers_with_forecast)
    if forecast_value == 0:
        return PortfolioForecastResponse(
            horizons=[], ticker_count=0, missing_tickers=sorted(position_values.keys())
        )

    # Weighted forecast aggregation — weights sum to 1.0 across covered tickers
    horizon_agg: dict[int, dict] = {}

    for ticker, value in position_values.items():
        if ticker not in tickers_with_forecast:
            continue
        weight = value / forecast_value  # KEY FIX: use forecast_value not total_value
        current_price = price_map.get(ticker)
        if not current_price:
            continue

        forecasts = forecasts_by_ticker[ticker]
        for fc in forecasts:
            if fc.horizon_days not in horizon_agg:
                horizon_agg[fc.horizon_days] = {
                    "return_sum": 0.0,
                    "lower_sum": 0.0,
                    "upper_sum": 0.0,
                }
            expected_return = fc.expected_return_pct / 100.0
            lower_return = fc.return_lower_pct / 100.0
            upper_return = fc.return_upper_pct / 100.0

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
        missing_tickers=missing_tickers,
    )


async def _fetch_evaluated_forecasts(
    ticker: str, since: date, session: AsyncSession
) -> list[ForecastResult]:
    """Fetch forecast results where evaluation has matured."""
    stmt = (
        select(ForecastResult)
        .where(
            ForecastResult.ticker == ticker,
            ForecastResult.error_pct.is_not(None),
            ForecastResult.forecast_date >= since,
        )
        .order_by(ForecastResult.target_date.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _fetch_forecast_date_prices(
    ticker: str, forecast_dates: list[date], session: AsyncSession
) -> dict[date, float]:
    """Batch-fetch closing prices at each forecast date.

    Fetches all prices in the date range and matches in Python.
    Handles weekends/holidays by using the most recent prior trading day.
    """
    if not forecast_dates:
        return {}

    min_date = min(forecast_dates) - timedelta(days=5)  # buffer for weekends
    max_date = max(forecast_dates)

    stmt = (
        select(func.date(StockPrice.time).label("price_date"), StockPrice.close)
        .where(
            StockPrice.ticker == ticker,
            func.date(StockPrice.time) >= min_date,
            func.date(StockPrice.time) <= max_date,
        )
        .order_by(StockPrice.time.asc())
    )
    result = await session.execute(stmt)
    all_prices = [(row.price_date, float(row.close)) for row in result]

    price_map: dict[date, float] = {}
    for fd in forecast_dates:
        best = None
        for price_date, close in all_prices:
            if price_date <= fd:
                best = close
            else:
                break
        if best is not None:
            price_map[fd] = best

    return price_map


@router.get(
    "/forecasts/{ticker}/track-record",
    response_model=ForecastTrackRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Forecast track record for a ticker",
    description=(
        "Returns evaluated forecasts with predicted vs actual prices, "
        "direction accuracy, and aggregate summary statistics."
    ),
)
async def get_forecast_track_record(
    ticker: TickerPath,
    request: Request,
    days: Annotated[
        int,
        Query(ge=30, le=730, description="Look-back window in days (default 365)"),
    ] = 365,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ForecastTrackRecordResponse:
    """Get forecast track record showing predicted vs actual outcomes.

    Args:
        ticker: Stock ticker symbol.
        request: FastAPI request (used for cache access).
        days: Look-back window in calendar days.
        current_user: Authenticated user (injected).
        session: Async DB session (injected).

    Returns:
        ForecastTrackRecordResponse with evaluations and summary.
    """
    ticker_upper = ticker.upper()

    # Check cache
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:forecast-track-record:{ticker_upper}:{days}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return ForecastTrackRecordResponse.model_validate_json(cached)

    since = date.today() - timedelta(days=days)

    rows = await _fetch_evaluated_forecasts(ticker_upper, since, session)

    if not rows:
        return ForecastTrackRecordResponse(
            ticker=ticker_upper,
            evaluations=[],
            summary=ForecastTrackRecordSummary(
                total_evaluated=0,
                direction_hit_rate=0.0,
                avg_error_pct=0.0,
                ci_containment_rate=0.0,
            ),
        )

    # Keep price_map available for future use; direction now uses return fields directly
    forecast_dates = list({r.forecast_date for r in rows})
    _ = await _fetch_forecast_date_prices(ticker_upper, forecast_dates, session)

    evaluations: list[ForecastEvaluation] = []
    direction_correct_count = 0
    ci_hits = 0
    total_error = 0.0

    for row in rows:
        direction_correct = bool(
            row.actual_return_pct is not None
            and row.expected_return_pct != 0
            and (row.expected_return_pct > 0) == (row.actual_return_pct > 0)
        )

        ci_hit = (
            row.actual_return_pct is not None
            and row.return_lower_pct <= row.actual_return_pct <= row.return_upper_pct
        )
        if ci_hit:
            ci_hits += 1
        if direction_correct:
            direction_correct_count += 1
        total_error += abs(row.error_pct) if row.error_pct else 0.0

        evaluations.append(
            ForecastEvaluation(
                forecast_date=row.forecast_date,
                target_date=row.target_date,
                horizon_days=row.horizon_days,
                expected_return_pct=row.expected_return_pct,
                return_lower_pct=row.return_lower_pct,
                return_upper_pct=row.return_upper_pct,
                actual_return_pct=row.actual_return_pct,
                error_pct=abs(row.error_pct) if row.error_pct else 0.0,
                direction_correct=direction_correct,
            )
        )

    total = len(evaluations)
    summary = ForecastTrackRecordSummary(
        total_evaluated=total,
        direction_hit_rate=round(direction_correct_count / total, 4) if total else 0.0,
        avg_error_pct=round(total_error / total, 4) if total else 0.0,
        ci_containment_rate=round(ci_hits / total, 4) if total else 0.0,
    )

    response = ForecastTrackRecordResponse(
        ticker=ticker_upper,
        evaluations=evaluations,
        summary=summary,
    )

    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), tier=CacheTier.STANDARD)

    return response


@router.get(
    "/forecasts/{ticker}",
    response_model=ForecastResponse,
    summary="Get forecast for a ticker",
)
async def get_ticker_forecast(
    ticker: TickerPath,
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

    from backend.services.forecast_engine import ForecastEngine

    # Fetch current price for implied_target_price calculation
    price_result = await db.execute(
        select(StockPrice.close)
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.time.desc())
        .limit(1)
    )
    current_price_scalar = price_result.scalar_one_or_none()
    if current_price_scalar is None:
        current_price = 0.0
    else:
        current_price = float(current_price_scalar)

    horizons = []
    for fc in forecasts:
        drivers = None
        if fc.drivers:
            drivers = [ForecastDriver(**d) for d in fc.drivers]

        implied_price = None
        if current_price > 0:
            implied_price = round(current_price * (1 + fc.expected_return_pct / 100), 2)

        horizons.append(
            ForecastHorizon(
                horizon_days=fc.horizon_days,
                expected_return_pct=fc.expected_return_pct,
                return_lower_pct=fc.return_lower_pct,
                return_upper_pct=fc.return_upper_pct,
                target_date=fc.target_date,
                direction=fc.direction,
                confidence=fc.confidence_score,
                confidence_level=ForecastEngine.confidence_level(fc.confidence_score),
                drivers=drivers,
                implied_target_price=implied_price,
                forecast_signal=fc.forecast_signal,
            )
        )

    horizons.sort(key=lambda h: h.horizon_days)

    # Build model_accuracy from model metrics
    model_accuracy = None
    if model and model.metrics:
        metrics = model.metrics
        if "direction_accuracy" in metrics:
            model_accuracy = ModelAccuracy(
                direction_hit_rate=metrics.get("direction_accuracy", 0.0),
                avg_error_pct=metrics.get("mean_absolute_error", 0.0),
                ci_containment_rate=metrics.get("ci_containment", 0.0),
                evaluated_count=metrics.get("evaluated_count", 0),
            )

    response = ForecastResponse(
        ticker=ticker,
        current_price=current_price,
        horizons=horizons,
        model_type=model.model_type if model else "none",
        model_accuracy=model_accuracy,
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
    request: Request,
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

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:forecast:sector:{sector}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return SectorForecastResponse.model_validate_json(cached)

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

        from backend.services.forecast_engine import ForecastEngine

        for fc in forecasts:
            drivers = None
            if fc.drivers:
                drivers = [ForecastDriver(**d) for d in fc.drivers]
            horizons.append(
                ForecastHorizon(
                    horizon_days=fc.horizon_days,
                    expected_return_pct=fc.expected_return_pct,
                    return_lower_pct=fc.return_lower_pct,
                    return_upper_pct=fc.return_upper_pct,
                    target_date=fc.target_date,
                    direction=fc.direction,
                    confidence=fc.confidence_score,
                    confidence_level=ForecastEngine.confidence_level(fc.confidence_score),
                    drivers=drivers,
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

    response = SectorForecastResponse(
        sector=sector.title(),
        etf_ticker=etf_ticker,
        horizons=horizons,
        user_tickers_in_sector=user_tickers,
    )
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, response.model_dump_json(), CacheTier.STANDARD)
    return response


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
