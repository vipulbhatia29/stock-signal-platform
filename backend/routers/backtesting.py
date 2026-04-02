"""Backtesting API — walk-forward validation results and accuracy badges."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.backtest import BacktestRun
from backend.models.user import User
from backend.schemas.backtesting import (
    BacktestRunResponse,
    BacktestSummaryItem,
    BacktestSummaryResponse,
    BacktestTriggerRequest,
    BacktestTriggerResponse,
    CalibrateTriggerRequest,
    CalibrateTriggerResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtests", tags=["backtesting"])

# NOTE: Literal routes (/summary/all, /run, /calibrate) MUST be declared
# before path-param routes (/{ticker}) to avoid FastAPI matching "summary"
# as a ticker value.


@router.get(
    "/summary/all",
    response_model=BacktestSummaryResponse,
    summary="Get backtest summary across all tickers",
)
async def get_backtest_summary(
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> BacktestSummaryResponse:
    """Get latest backtest metrics per ticker+horizon, sorted by MAPE (best first).

    Args:
        limit: Maximum number of results.
        offset: Pagination offset.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        Summary with items and total count.
    """
    # Count total distinct (ticker, horizon) pairs
    count_result = await db.execute(
        select(func.count()).select_from(
            select(BacktestRun.ticker, BacktestRun.horizon_days)
            .group_by(BacktestRun.ticker, BacktestRun.horizon_days)
            .subquery()
        )
    )
    total = count_result.scalar() or 0

    # Get latest run per ticker+horizon using subquery for max created_at
    latest_subq = (
        select(
            BacktestRun.ticker,
            BacktestRun.horizon_days,
            func.max(BacktestRun.created_at).label("max_created"),
        )
        .group_by(BacktestRun.ticker, BacktestRun.horizon_days)
        .subquery()
    )

    result = await db.execute(
        select(BacktestRun)
        .join(
            latest_subq,
            (BacktestRun.ticker == latest_subq.c.ticker)
            & (BacktestRun.horizon_days == latest_subq.c.horizon_days)
            & (BacktestRun.created_at == latest_subq.c.max_created),
        )
        .order_by(BacktestRun.mape.asc())
        .offset(offset)
        .limit(limit)
    )
    runs = result.scalars().all()

    items = [BacktestSummaryItem.model_validate(r) for r in runs]
    return BacktestSummaryResponse(items=items, total=total)


@router.post(
    "/run",
    response_model=BacktestTriggerResponse,
    summary="Trigger a backtest run (admin only)",
    status_code=202,
)
async def trigger_backtest(
    request: BacktestTriggerRequest,
    current_user: User = Depends(get_current_user),
) -> BacktestTriggerResponse:
    """Trigger a walk-forward backtest for a ticker or all tickers.

    Requires admin role. The backtest runs asynchronously via Celery.

    Args:
        request: Backtest trigger parameters.
        current_user: Authenticated user (must be admin).

    Returns:
        Task ID for tracking progress.
    """
    require_admin(current_user)

    from backend.tasks.forecasting import run_backtest_task

    task = run_backtest_task.delay(
        ticker=request.ticker,
        horizon_days=request.horizon_days,
    )
    logger.info(
        "Backtest triggered by %s: ticker=%s, horizon=%d",
        current_user.email,
        request.ticker or "all",
        request.horizon_days,
    )
    return BacktestTriggerResponse(task_id=task.id)


@router.post(
    "/calibrate",
    response_model=CalibrateTriggerResponse,
    summary="Trigger seasonality calibration (admin only)",
    status_code=202,
)
async def trigger_calibration(
    request: CalibrateTriggerRequest,
    current_user: User = Depends(get_current_user),
) -> CalibrateTriggerResponse:
    """Trigger seasonality calibration for a ticker or all tickers.

    Requires admin role. Calibration runs asynchronously via Celery.

    Args:
        request: Calibration trigger parameters.
        current_user: Authenticated user (must be admin).

    Returns:
        Task ID for tracking progress.
    """
    require_admin(current_user)

    from backend.tasks.forecasting import calibrate_seasonality_task

    task = calibrate_seasonality_task.delay(ticker=request.ticker)
    logger.info(
        "Calibration triggered by %s: ticker=%s",
        current_user.email,
        request.ticker or "all",
    )
    return CalibrateTriggerResponse(task_id=task.id)


@router.get(
    "/{ticker}",
    response_model=BacktestRunResponse,
    summary="Get latest backtest result for a ticker",
)
async def get_backtest_result(
    ticker: str,
    horizon_days: int = Query(90, description="Forecast horizon"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> BacktestRunResponse:
    """Get the most recent backtest result for a specific ticker and horizon.

    Args:
        ticker: Stock ticker symbol.
        horizon_days: Forecast horizon in days.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        Latest backtest result.

    Raises:
        HTTPException: 404 if no backtest found.
    """
    result = await db.execute(
        select(BacktestRun)
        .where(
            BacktestRun.ticker == ticker.upper(),
            BacktestRun.horizon_days == horizon_days,
        )
        .order_by(BacktestRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="No backtest found for ticker")
    return BacktestRunResponse.model_validate(run)


@router.get(
    "/{ticker}/history",
    response_model=list[BacktestRunResponse],
    summary="Get backtest history for a ticker",
)
async def get_backtest_history(
    ticker: str,
    horizon_days: int = Query(90, description="Forecast horizon"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> list[BacktestRunResponse]:
    """Get historical backtest runs for a ticker, newest first.

    Args:
        ticker: Stock ticker symbol.
        horizon_days: Forecast horizon in days.
        limit: Maximum number of results.
        offset: Pagination offset.
        db: Async database session.
        current_user: Authenticated user.

    Returns:
        List of backtest results.
    """
    result = await db.execute(
        select(BacktestRun)
        .where(
            BacktestRun.ticker == ticker.upper(),
            BacktestRun.horizon_days == horizon_days,
        )
        .order_by(BacktestRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    runs = result.scalars().all()
    return [BacktestRunResponse.model_validate(r) for r in runs]
