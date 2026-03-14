"""Portfolio API endpoints: transactions, positions, and summary."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.portfolio import Transaction
from backend.models.user import User
from backend.schemas.portfolio import (
    PortfolioSummaryResponse,
    PositionResponse,
    TransactionCreate,
    TransactionResponse,
)
from backend.tools.portfolio import (
    _get_transactions_for_ticker,
    _run_fifo,
    get_or_create_portfolio,
    get_portfolio_summary,
    get_positions_with_pnl,
    recompute_position,
)

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


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="Get current positions with live P&L",
)
async def list_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PositionResponse]:
    """Return all open positions with current price and unrealized P&L."""
    portfolio = await get_or_create_portfolio(current_user.id, db)
    return await get_positions_with_pnl(portfolio.id, db)


@router.get(
    "/summary",
    response_model=PortfolioSummaryResponse,
    summary="Get portfolio KPI totals and sector allocation",
)
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> PortfolioSummaryResponse:
    """Return total value, cost basis, unrealized P&L, and sector breakdown."""
    portfolio = await get_or_create_portfolio(current_user.id, db)
    return await get_portfolio_summary(portfolio.id, db)
