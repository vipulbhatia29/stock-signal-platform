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
from backend.models.portfolio import Transaction
from backend.models.signal import SignalSnapshot
from backend.models.user import User
from backend.routers.preferences import _get_or_create_preference
from backend.schemas.portfolio import (
    DivestmentAlert,
    DividendSummaryResponse,
    PortfolioSnapshotResponse,
    PortfolioSummaryResponse,
    PositionWithAlerts,
    RebalancingResponse,
    RebalancingSuggestion,
    TransactionCreate,
    TransactionResponse,
)
from backend.tools.divestment import check_divestment_rules
from backend.tools.dividends import get_dividend_summary
from backend.tools.market_data import get_latest_price
from backend.tools.portfolio import (
    _get_transactions_for_ticker,
    _run_fifo,
    get_or_create_portfolio,
    get_portfolio_history,
    get_portfolio_summary,
    get_positions_with_pnl,
    recompute_position,
)
from backend.tools.recommendations import calculate_position_size

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
    response_model=list[TransactionResponse],
    summary="Get transaction history",
)
async def list_transactions(
    ticker: str | None = Query(None, description="Filter by ticker"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[TransactionResponse]:
    """Return all transactions sorted by date descending.

    Optionally filter by ticker symbol.
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)

    stmt = (
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.transacted_at.desc())
    )
    if ticker:
        stmt = stmt.where(Transaction.ticker == ticker.upper().strip())

    result = await db.execute(stmt)
    txns = result.scalars().all()
    return [TransactionResponse.model_validate(t) for t in txns]


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

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.portfolio_id == portfolio.id,
        )
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")

    ticker = txn.ticker

    # Pre-delete simulation: run FIFO without this transaction (ID-based exclusion)
    all_txns = await _get_transactions_for_ticker(portfolio.id, ticker, db)
    remaining = [t for t in all_txns if t["id"] != str(txn.id)]
    try:
        _run_fifo(remaining)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot delete: removing this transaction would leave "
                "a later SELL without sufficient shares."
            ),
        )

    await db.delete(txn)
    await recompute_position(portfolio.id, ticker, db)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PositionWithAlerts]:
    """Return all open positions with P&L and divestment alerts.

    Alerts are computed on-demand using the user's preference thresholds.
    Three queries: positions, user preferences, latest signals.
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)
    positions = await get_positions_with_pnl(portfolio.id, db)

    if not positions:
        return []

    # Query 2: user preferences
    prefs = await _get_or_create_preference(current_user.id, db)

    # Query 3: bulk-fetch latest composite_score for held tickers
    tickers = [p.ticker for p in positions]
    from sqlalchemy import func

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
    """Compute rebalancing suggestions for all open positions.

    For each held position, calculates how much the user would need to invest
    to bring it to its equal-weight target (capped by max_position_pct and
    max_sector_pct from UserPreference).

    Available cash is computed as total_value - sum(market_values) — i.e.,
    what is not currently invested. Phase 3.5: no explicit cash account exists,
    so available_cash is reported as 0.0.
    """
    portfolio = await get_or_create_portfolio(current_user.id, db)
    pref = await _get_or_create_preference(current_user.id, db)

    positions = await get_positions_with_pnl(portfolio.id, db)

    if not positions:
        return RebalancingResponse(
            total_value=0.0,
            available_cash=0.0,
            num_positions=0,
            suggestions=[],
        )

    # Compute portfolio totals
    total_value = sum(p.market_value or 0.0 for p in positions)
    available_cash = 0.0  # no cash account in Phase 3.5

    num_positions = len(positions)

    # Build sector allocation map for sector cap checks
    sector_totals: dict[str, float] = {}
    for p in positions:
        if p.sector and p.market_value:
            sector_totals[p.sector] = sector_totals.get(p.sector, 0.0) + p.market_value
    sector_pct_map: dict[str, float] = {
        sector: (val / total_value * 100) if total_value > 0 else 0.0
        for sector, val in sector_totals.items()
    }

    suggestions = []
    for pos in positions:
        alloc = pos.allocation_pct or 0.0
        sector_alloc = sector_pct_map.get(pos.sector or "", 0.0)

        amount = calculate_position_size(
            ticker=pos.ticker,
            current_allocation_pct=alloc,
            total_value=total_value,
            available_cash=available_cash,
            num_target_positions=num_positions,
            max_position_pct=pref.max_position_pct,
            sector_allocation_pct=sector_alloc,
            max_sector_pct=pref.max_sector_pct,
        )

        equal_weight_pct = 100.0 / max(num_positions, 1)
        target_pct = min(pref.max_position_pct, equal_weight_pct)

        if sector_alloc >= pref.max_sector_pct:
            action = "AT_CAP"
            reason = f"Sector {pos.sector or 'Unknown'} is at the {pref.max_sector_pct:.0f}% cap"
        elif amount > 0:
            action = "BUY_MORE"
            reason = (
                f"Under-weight ({alloc:.1f}% vs {target_pct:.1f}% target). "
                f"Add ${amount:,.2f} to reach target."
            )
        else:
            action = "HOLD"
            reason = f"At or above target allocation ({alloc:.1f}% \u2265 {target_pct:.1f}%)"

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

    # Sort: BUY_MORE first (highest gap), then HOLD, then AT_CAP
    action_order = {"BUY_MORE": 0, "HOLD": 1, "AT_CAP": 2}
    suggestions.sort(key=lambda s: (action_order.get(s.action, 9), -s.suggested_amount))

    return RebalancingResponse(
        total_value=total_value,
        available_cash=available_cash,
        num_positions=num_positions,
        suggestions=suggestions,
    )


@router.get(
    "/dividends/{ticker}",
    response_model=DividendSummaryResponse,
    summary="Get dividend history and summary for a ticker",
)
async def get_dividends_for_ticker(
    ticker: str,
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
    from datetime import datetime, timedelta, timezone

    from backend.models.portfolio import Portfolio
    from backend.models.portfolio_health import PortfolioHealthSnapshot
    from backend.schemas.portfolio_health import PortfolioHealthSnapshotResponse

    portfolio = (
        await db.execute(select(Portfolio).where(Portfolio.user_id == user.id))
    ).scalar_one_or_none()
    if not portfolio:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PortfolioHealthSnapshot)
        .where(
            PortfolioHealthSnapshot.portfolio_id == portfolio.id,
            PortfolioHealthSnapshot.snapshot_date >= cutoff,
        )
        .order_by(PortfolioHealthSnapshot.snapshot_date.asc())
    )
    snapshots = result.scalars().all()
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
