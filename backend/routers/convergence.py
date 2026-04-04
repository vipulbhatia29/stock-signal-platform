"""Signal convergence API — traffic lights, divergence alerts, rationale."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.portfolio import Portfolio
from backend.models.user import User
from backend.schemas.convergence import (
    ConvergenceHistoryResponse,
    ConvergenceHistoryRow,
    ConvergenceLabelEnum,
    ConvergenceResponse,
    DirectionEnum,
    DivergenceAlert,
    PortfolioConvergenceResponse,
    PortfolioPositionConvergence,
    SectorConvergenceResponse,
    SectorTickerConvergence,
    SignalDirectionDetail,
)
from backend.services.rationale import RationaleGenerator
from backend.services.signal_convergence import (
    DivergenceInfo,
    SignalConvergenceService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/convergence", tags=["convergence"])


def _build_divergence_alert(div: DivergenceInfo) -> DivergenceAlert:
    """Map service-layer DivergenceInfo to schema DivergenceAlert.

    Args:
        div: DivergenceInfo dataclass from the service layer.

    Returns:
        DivergenceAlert Pydantic schema.
    """
    fc_dir = DirectionEnum(div.forecast_direction) if div.forecast_direction else None
    tech_dir = DirectionEnum(div.technical_majority) if div.technical_majority else None
    return DivergenceAlert(
        is_divergent=div.is_divergent,
        forecast_direction=fc_dir,
        technical_majority=tech_dir,
        historical_hit_rate=div.historical_hit_rate,
        sample_count=div.sample_count,
    )


# ──────────────────────────────────────────────────────────────────────
# GET /convergence/portfolio/{portfolio_id}
# NOTE: Must be declared BEFORE /{ticker} to avoid route collision.
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/portfolio/{portfolio_id}",
    response_model=PortfolioConvergenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Portfolio convergence summary",
    description=(
        "Returns per-position convergence labels with weight-adjusted "
        "bullish/bearish/mixed percentages."
    ),
)
async def get_portfolio_convergence(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> PortfolioConvergenceResponse:
    """Get convergence summary for a portfolio.

    Args:
        portfolio_id: UUID of the portfolio.
        current_user: Authenticated user (injected).
        session: Async DB session (injected).

    Returns:
        PortfolioConvergenceResponse with per-position convergence and aggregation.
    """
    # Verify portfolio ownership
    result = await session.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    service = SignalConvergenceService()
    position_convergences = await service.get_portfolio_convergence(portfolio_id, session)

    if not position_convergences:
        return PortfolioConvergenceResponse(
            portfolio_id=portfolio_id,
            date=datetime.now(timezone.utc).date(),
            positions=[],
            bullish_pct=0.0,
            bearish_pct=0.0,
            mixed_pct=0.0,
            divergent_positions=[],
        )

    # Build per-position and aggregate
    positions: list[PortfolioPositionConvergence] = []
    bullish_weight = 0.0
    bearish_weight = 0.0
    mixed_weight = 0.0
    divergent_tickers: list[str] = []

    for conv, weight in position_convergences:
        positions.append(
            PortfolioPositionConvergence(
                ticker=conv.ticker,
                weight=round(weight, 4),
                convergence_label=ConvergenceLabelEnum(conv.convergence_label),
                signals_aligned=conv.signals_aligned,
                divergence=_build_divergence_alert(conv.divergence),
            )
        )

        if conv.convergence_label in ("strong_bull", "weak_bull"):
            bullish_weight += weight
        elif conv.convergence_label in ("strong_bear", "weak_bear"):
            bearish_weight += weight
        else:
            mixed_weight += weight

        if conv.divergence.is_divergent:
            divergent_tickers.append(conv.ticker)

    return PortfolioConvergenceResponse(
        portfolio_id=portfolio_id,
        date=datetime.now(timezone.utc).date(),
        positions=positions,
        bullish_pct=round(bullish_weight, 4),
        bearish_pct=round(bearish_weight, 4),
        mixed_pct=round(mixed_weight, 4),
        divergent_positions=divergent_tickers,
    )


# ──────────────────────────────────────────────────────────────────────
# GET /convergence/{ticker}/history
# NOTE: Must be declared BEFORE /{ticker} to avoid route collision.
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{ticker}/history",
    response_model=ConvergenceHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Convergence history for a ticker",
    description="Returns historical convergence labels over time, paginated.",
)
async def get_convergence_history(
    ticker: str,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Look-back window in calendar days"),
    ] = 90,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Page size"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Page offset"),
    ] = 0,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ConvergenceHistoryResponse:
    """Get historical convergence data for a ticker.

    Args:
        ticker: Stock ticker symbol.
        days: Look-back window.
        limit: Page size.
        offset: Page offset.
        current_user: Authenticated user (injected).
        session: Async DB session (injected).

    Returns:
        ConvergenceHistoryResponse with paginated rows.
    """
    ticker_upper = ticker.upper()
    service = SignalConvergenceService()

    try:
        rows, total = await service.get_convergence_history(
            ticker_upper, session, days=days, limit=limit, offset=offset
        )
    except Exception:
        logger.exception("Failed to fetch convergence history for %s", ticker_upper)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve convergence history.",
        )

    return ConvergenceHistoryResponse(
        ticker=ticker_upper,
        data=[
            ConvergenceHistoryRow(
                date=row.date,
                convergence_label=ConvergenceLabelEnum(row.convergence_label),
                signals_aligned=row.signals_aligned,
                composite_score=row.composite_score,
                actual_return_90d=row.actual_return_90d,
                actual_return_180d=row.actual_return_180d,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


# ──────────────────────────────────────────────────────────────────────
# GET /convergence/{ticker}  (catch-all — MUST be last)
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{ticker}",
    response_model=ConvergenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Signal convergence for a single ticker",
    description=(
        "Returns traffic-light signal directions, convergence label, "
        "divergence alert, and a human-readable rationale."
    ),
)
async def get_ticker_convergence(
    ticker: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ConvergenceResponse:
    """Get convergence analysis for a single ticker.

    Args:
        ticker: Stock ticker symbol.
        current_user: Authenticated user (injected).
        session: Async DB session (injected).

    Returns:
        ConvergenceResponse with signals, label, divergence, rationale.
    """
    ticker_upper = ticker.upper()
    service = SignalConvergenceService()

    convergence = await service.get_ticker_convergence(ticker_upper, session)
    if convergence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No signal data found for this ticker.",
        )

    # Enrich divergence with historical hit rate
    if convergence.divergence.is_divergent:
        hit_rate, sample_count = await service.compute_divergence_hit_rate(
            ticker_upper,
            convergence.divergence.forecast_direction or "",
            convergence.divergence.technical_majority or "",
            session,
        )
        convergence.divergence.historical_hit_rate = hit_rate
        convergence.divergence.sample_count = sample_count

    # Generate rationale (template-based, no LLM for single ticker in hot path)
    rationale_gen = RationaleGenerator()
    rationale = await rationale_gen.generate(
        signals=convergence.signals,
        convergence_label=convergence.convergence_label,
        divergence=convergence.divergence,
        ticker=ticker_upper,
    )

    return ConvergenceResponse(
        ticker=convergence.ticker,
        date=convergence.date,
        signals=[
            SignalDirectionDetail(
                signal=s.signal,
                direction=DirectionEnum(s.direction),
                value=s.value,
            )
            for s in convergence.signals
        ],
        signals_aligned=convergence.signals_aligned,
        convergence_label=ConvergenceLabelEnum(convergence.convergence_label),
        composite_score=convergence.composite_score,
        divergence=_build_divergence_alert(convergence.divergence),
        rationale=rationale,
    )


# ──────────────────────────────────────────────────────────────────────
# GET /sectors/{sector}/convergence  (separate router, own prefix)
# ──────────────────────────────────────────────────────────────────────

sector_router = APIRouter(prefix="/sectors", tags=["convergence"])


@sector_router.get(
    "/{sector}/convergence",
    response_model=SectorConvergenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Sector convergence summary",
    description=("Equal-weight aggregated convergence for all active tickers in a sector."),
)
async def get_sector_convergence(
    sector: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> SectorConvergenceResponse:
    """Get convergence summary for a sector.

    Args:
        sector: Sector name (e.g. "Technology").
        current_user: Authenticated user (injected).
        session: Async DB session (injected).

    Returns:
        SectorConvergenceResponse with equal-weight aggregation.
    """
    service = SignalConvergenceService()
    convergences = await service.get_sector_convergence(sector, session)

    if not convergences:
        return SectorConvergenceResponse(
            sector=sector,
            date=datetime.now(timezone.utc).date(),
            tickers=[],
            bullish_pct=0.0,
            bearish_pct=0.0,
            mixed_pct=0.0,
            ticker_count=0,
        )

    tickers_out: list[SectorTickerConvergence] = []
    bullish_count = 0
    bearish_count = 0
    mixed_count = 0

    for conv in convergences:
        tickers_out.append(
            SectorTickerConvergence(
                ticker=conv.ticker,
                convergence_label=ConvergenceLabelEnum(conv.convergence_label),
                signals_aligned=conv.signals_aligned,
            )
        )
        if conv.convergence_label in ("strong_bull", "weak_bull"):
            bullish_count += 1
        elif conv.convergence_label in ("strong_bear", "weak_bear"):
            bearish_count += 1
        else:
            mixed_count += 1

    total = len(convergences)
    return SectorConvergenceResponse(
        sector=sector,
        date=datetime.now(timezone.utc).date(),
        tickers=tickers_out,
        bullish_pct=round(bullish_count / total, 4) if total else 0.0,
        bearish_pct=round(bearish_count / total, 4) if total else 0.0,
        mixed_pct=round(mixed_count / total, 4) if total else 0.0,
        ticker_count=total,
    )
