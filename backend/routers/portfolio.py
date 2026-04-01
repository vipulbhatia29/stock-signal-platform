"""Portfolio API endpoints: transactions, positions, and summary."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.signal import SignalSnapshot
from backend.models.user import User
from backend.routers.preferences import _get_or_create_preference
from backend.schemas.portfolio import (
    DivestmentAlert,
    DividendSummaryResponse,
    PortfolioAnalyticsResponse,
    PortfolioSnapshotResponse,
    PortfolioSummaryResponse,
    PositionWithAlerts,
    RebalancingResponse,
    RebalancingSuggestion,
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
)
from backend.services.exceptions import PortfolioNotFoundError
from backend.services.portfolio import (
    _get_transactions_for_ticker,
    _run_fifo,
    get_or_create_portfolio,
    get_portfolio_history,
    get_portfolio_summary,
    get_positions_with_pnl,
    recompute_position,
)
from backend.services.portfolio import delete_transaction as svc_delete_transaction
from backend.services.portfolio import get_health_history as svc_get_health_history
from backend.services.portfolio import list_transactions as svc_list_transactions
from backend.services.recommendations import calculate_position_size
from backend.services.stock_data import get_latest_price
from backend.tools.divestment import check_divestment_rules
from backend.tools.dividends import get_dividend_summary
from backend.validation import TickerPath

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a BUY or SELL transaction",
)
async def create_transaction(
    body: TransactionCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TransactionResponse:
    """Log a BUY or SELL trade and recompute positions via FIFO.

    Returns the created transaction. Returns 422 if:
    - Ticker not found in stocks table
    - SELL exceeds available shares
    """
    from backend.models.portfolio import Transaction

    portfolio = await get_or_create_portfolio(current_user.id, db)

    # Pre-validate SELL: check it won't exceed current open shares
    if body.transaction_type == "SELL":
        existing = await _get_transactions_for_ticker(portfolio.id, body.ticker, db)
        try:
            current = _run_fifo(existing)
        except ValueError:
            current = {"shares": 0}
        if float(body.shares) > float(current.get("shares", 0)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot sell {body.shares} shares of {body.ticker}: "
                f"only {current.get('shares', 0)} shares held.",
            )

    txn = Transaction(
        portfolio_id=portfolio.id,
        ticker=body.ticker,
        transaction_type=body.transaction_type,
        shares=body.shares,
        price_per_share=body.price_per_share,
        transacted_at=body.transacted_at,
        notes=body.notes,
    )
    db.add(txn)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if "foreign key" in str(exc.orig).lower() and "ticker" in str(exc.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Ticker '{body.ticker}' not found. "
                    "Add it to your watchlist first to ingest it."
                ),
            ) from exc
        raise

    await recompute_position(portfolio.id, body.ticker, db)
    await db.commit()
    await db.refresh(txn)
    logger.info(
        "Logged %s %s %s for user %s",
        body.transaction_type,
        body.shares,
        body.ticker,
        current_user.id,
    )
    cache = getattr(request.app.state, "cache", None)
    if cache:
        await cache.invalidate_user(str(current_user.id))
    return TransactionResponse.model_validate(txn)


@router.get(
    "/transactions",
    response_model=TransactionListResponse,
    summary="Get transaction history",
)
async def list_transactions(
    ticker: str | None = Query(None, description="Filter by ticker"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> TransactionListResponse:
    """Return paginated transactions sorted by date descending.

    Optionally filter by ticker symbol.
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)
    txns, total = await svc_list_transactions(
        portfolio.id, db, ticker=ticker, limit=limit, offset=offset
    )

    return TransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in txns],
        total=total,
    )


@router.delete(
    "/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a transaction",
)
async def delete_transaction(
    transaction_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """Remove a transaction after validating it won't strand a later SELL.

    Returns 422 if removing this transaction would leave any SELL
    without sufficient BUY lots.
    Returns 404 if transaction not found or belongs to another user.
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)

    try:
        await svc_delete_transaction(portfolio.id, transaction_id, db)
    except PortfolioNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot delete: removing this transaction would leave "
                "a later SELL without sufficient shares."
            ),
        )

    await db.commit()
    logger.info("Deleted transaction %s for user %s", transaction_id, current_user.id)
    cache = getattr(request.app.state, "cache", None)
    if cache:
        await cache.invalidate_user(str(current_user.id))


@router.get(
    "/positions",
    response_model=list[PositionWithAlerts],
    summary="Get current positions with live P&L and divestment alerts",
)
async def list_positions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PositionWithAlerts]:
    """Return all open positions with P&L and divestment alerts.

    Alerts are computed on-demand using the user's preference thresholds.
    Three queries: positions, user preferences, latest signals.
    """
    import json

    from sqlalchemy import func, select

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"user:{current_user.id}:positions"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

    portfolio = await get_or_create_portfolio(current_user.id, db)
    positions = await get_positions_with_pnl(portfolio.id, db)

    if not positions:
        return []

    # Query 2: user preferences
    prefs = await _get_or_create_preference(current_user.id, db)

    # Query 3: bulk-fetch latest composite_score for held tickers
    tickers = [p.ticker for p in positions]

    subq = (
        select(
            SignalSnapshot.ticker,
            func.max(SignalSnapshot.computed_at).label("latest"),
        )
        .where(SignalSnapshot.ticker.in_(tickers))
        .group_by(SignalSnapshot.ticker)
        .subquery()
    )
    signal_result = await db.execute(
        select(SignalSnapshot.ticker, SignalSnapshot.composite_score).join(
            subq,
            (SignalSnapshot.ticker == subq.c.ticker)
            & (SignalSnapshot.computed_at == subq.c.latest),
        )
    )
    signal_map: dict[str, float | None] = {row.ticker: row.composite_score for row in signal_result}

    # Build sector allocations from positions in-memory
    total_value = sum(p.market_value or 0 for p in positions)
    sector_buckets: dict[str, float] = {}
    for p in positions:
        sector = p.sector or "Unknown"
        sector_buckets[sector] = sector_buckets.get(sector, 0.0) + (p.market_value or 0)
    sector_allocations = [
        {"sector": s, "pct": round(v / total_value * 100, 2) if total_value > 0 else 0.0}
        for s, v in sector_buckets.items()
    ]

    # Check rules for each position
    result: list[PositionWithAlerts] = []
    for p in positions:
        pos_dict = {
            "ticker": p.ticker,
            "unrealized_pnl_pct": p.unrealized_pnl_pct,
            "allocation_pct": p.allocation_pct,
            "sector": p.sector,
        }
        signal = {"composite_score": signal_map.get(p.ticker)} if p.ticker in signal_map else None
        alerts_raw = check_divestment_rules(pos_dict, sector_allocations, signal, prefs)
        alerts = [DivestmentAlert(**a) for a in alerts_raw]
        result.append(
            PositionWithAlerts(
                **p.model_dump(),
                alerts=alerts,
            )
        )

    if cache:
        from backend.services.cache import CacheTier

        serialized = json.dumps([r.model_dump(mode="json") for r in result], default=str)
        await cache.set(cache_key, serialized, CacheTier.VOLATILE)
    return result


@router.get(
    "/summary",
    response_model=PortfolioSummaryResponse,
    summary="Get portfolio KPI totals and sector allocation",
)
async def get_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> PortfolioSummaryResponse:
    """Return total value, cost basis, unrealized P&L, and sector breakdown.

    Uses the user's max_sector_pct preference for the over_limit flag.
    """
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"user:{current_user.id}:portfolio:summary"
    if cache:
        from backend.services.cache import CacheTier

        cached = await cache.get(cache_key)
        if cached:
            return PortfolioSummaryResponse.model_validate_json(cached)

    portfolio = await get_or_create_portfolio(current_user.id, db)
    prefs = await _get_or_create_preference(current_user.id, db)
    result = await get_portfolio_summary(portfolio.id, db, max_sector_pct=prefs.max_sector_pct)
    if cache:
        from backend.services.cache import CacheTier

        await cache.set(cache_key, result.model_dump_json(), tier=CacheTier.VOLATILE)
    return result


@router.get(
    "/history",
    response_model=list[PortfolioSnapshotResponse],
    summary="Get portfolio value history",
)
async def get_history(
    days: int = Query(365, ge=1, le=3650, description="Days of history to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PortfolioSnapshotResponse]:
    """Return daily portfolio value snapshots for the chart.

    Captured by the Celery Beat daily snapshot task. Returns empty list
    if no snapshots exist yet.
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)
    snapshots = await get_portfolio_history(portfolio.id, db, days=days)
    return [PortfolioSnapshotResponse.model_validate(s) for s in snapshots]


@router.get(
    "/rebalancing",
    response_model=RebalancingResponse,
    summary="Get rebalancing suggestions for all open positions",
)
async def get_rebalancing(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RebalancingResponse:
    """Return optimized rebalancing suggestions from materialized data.

    Reads from the `rebalancing_suggestions` table (populated by the nightly
    pipeline). Falls back to on-the-fly equal-weight calculation if no
    materialized data exists yet.
    """
    from backend.models.portfolio import RebalancingSuggestion as RebalSuggModel

    portfolio = await get_or_create_portfolio(current_user.id, db)
    positions = await get_positions_with_pnl(portfolio.id, db)

    if not positions:
        return RebalancingResponse(
            total_value=0.0,
            available_cash=0.0,
            num_positions=0,
            suggestions=[],
        )

    total_value = sum(p.market_value or 0.0 for p in positions)

    # Try materialized suggestions first
    result = await db.execute(
        select(RebalSuggModel)
        .where(RebalSuggModel.portfolio_id == portfolio.id)
        .order_by(RebalSuggModel.delta_dollars.desc())
    )
    materialized = list(result.scalars().all())

    if materialized:
        suggestions = [
            RebalancingSuggestion(
                ticker=s.ticker,
                action=s.action,
                current_allocation_pct=round(s.current_weight * 100, 2),
                target_allocation_pct=round(s.target_weight * 100, 2),
                suggested_amount=abs(s.delta_dollars),
                reason=(
                    f"Strategy: {s.strategy}. "
                    f"Target {s.target_weight:.1%} vs current {s.current_weight:.1%}."
                ),
            )
            for s in materialized
        ]
    else:
        # Fallback: equal-weight on-the-fly (no materialized data yet)
        pref = await _get_or_create_preference(current_user.id, db)
        num_positions = len(positions)
        suggestions = []
        for pos in positions:
            alloc = pos.allocation_pct or 0.0
            amount = calculate_position_size(
                ticker=pos.ticker,
                current_allocation_pct=alloc,
                total_value=total_value,
                available_cash=0.0,
                num_target_positions=num_positions,
                max_position_pct=pref.max_position_pct,
                sector_allocation_pct=0.0,
                max_sector_pct=pref.max_sector_pct,
            )
            equal_weight_pct = 100.0 / max(num_positions, 1)
            target_pct = min(pref.max_position_pct, equal_weight_pct)
            action = "BUY_MORE" if amount > 0 else "HOLD"
            reason = f"Equal-weight target {target_pct:.1f}%"
            suggestions.append(
                RebalancingSuggestion(
                    ticker=pos.ticker,
                    action=action,
                    current_allocation_pct=alloc,
                    target_allocation_pct=round(target_pct, 2),
                    suggested_amount=amount,
                    reason=reason,
                )
            )

    return RebalancingResponse(
        total_value=total_value,
        available_cash=0.0,
        num_positions=len(positions),
        suggestions=suggestions,
    )


@router.get(
    "/dividends/{ticker}",
    response_model=DividendSummaryResponse,
    summary="Get dividend history and summary for a ticker",
)
async def get_dividends_for_ticker(
    ticker: TickerPath,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> DividendSummaryResponse:
    """Return dividend payment history and summary stats for a ticker.

    Includes total received, trailing-12-month annual dividends,
    dividend yield (if price data available), and full payment history.
    """
    price = await get_latest_price(ticker, db)
    summary = await get_dividend_summary(ticker, db, current_price=price)
    return DividendSummaryResponse(**summary)


@router.get("/health/history")
async def get_health_history(
    days: int = Query(default=90, le=365, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list:
    """Get portfolio health score history for trend chart.

    Returns daily health snapshots for the specified number of days.
    """
    from backend.models.portfolio import Portfolio
    from backend.schemas.portfolio_health import PortfolioHealthSnapshotResponse

    portfolio = (
        await db.execute(select(Portfolio).where(Portfolio.user_id == user.id))
    ).scalar_one_or_none()
    if not portfolio:
        return []

    snapshots = await svc_get_health_history(portfolio.id, db, days=days)
    return [
        PortfolioHealthSnapshotResponse(
            snapshot_date=s.snapshot_date.isoformat(),
            health_score=s.health_score,
            grade=s.grade,
            diversification_score=s.diversification_score,
            signal_quality_score=s.signal_quality_score,
            risk_score=s.risk_score,
            income_score=s.income_score,
            sector_balance_score=s.sector_balance_score,
            hhi=s.hhi,
            weighted_beta=s.weighted_beta,
            weighted_sharpe=s.weighted_sharpe,
            weighted_yield=s.weighted_yield,
            position_count=s.position_count,
        )
        for s in snapshots
    ]


@router.get("/health")
async def get_portfolio_health(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get portfolio health score with component breakdown.

    Computes a 0-10 health score from diversification, signal quality,
    risk, income, and sector balance.
    """
    from backend.services.cache import CacheTier
    from backend.tools.portfolio_health import PortfolioHealthTool

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"user:{user.id}:portfolio_health"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            import json

            return json.loads(cached)

    tool = PortfolioHealthTool()
    result = await tool.execute({})

    if result.status == "ok" and result.data and cache:
        import json

        await cache.set(cache_key, json.dumps(result.data, default=str), CacheTier.VOLATILE)

    return result.data or {"error": result.error}


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio Analytics (QuantStats)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/analytics",
    response_model=PortfolioAnalyticsResponse,
    summary="Portfolio-level QuantStats analytics",
)
async def get_portfolio_analytics(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(get_current_user),
) -> PortfolioAnalyticsResponse:
    """Return QuantStats metrics from the latest portfolio snapshot."""
    from backend.models.portfolio import PortfolioSnapshot

    portfolio = await get_or_create_portfolio(user.id, db)

    result = await db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.portfolio_id == portfolio.id)
        .order_by(PortfolioSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if snapshot is None:
        return PortfolioAnalyticsResponse()

    return PortfolioAnalyticsResponse(
        sharpe=snapshot.sharpe,
        sortino=snapshot.sortino,
        max_drawdown=snapshot.max_drawdown,
        max_drawdown_duration=snapshot.max_drawdown_duration,
        calmar=snapshot.calmar,
        alpha=snapshot.alpha,
        beta=snapshot.beta,
        var_95=snapshot.var_95,
        cagr=snapshot.cagr,
        data_days=snapshot.data_days,
    )
