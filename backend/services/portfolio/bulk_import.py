"""Bulk CSV import service for portfolio transactions (Spec C.5)."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.stock import Stock
from backend.schemas.portfolio import BulkTransactionError, BulkTransactionRow

logger = logging.getLogger(__name__)

MAX_ROWS = 500
MAX_FILE_SIZE = 256 * 1024  # 256 KB
REQUIRED_COLUMNS = {"ticker", "transaction_type", "shares", "price_per_share", "transacted_at"}
INGEST_CONCURRENCY = 5


def parse_csv(content: str) -> tuple[list[BulkTransactionRow], list[BulkTransactionError]]:
    """Parse CSV content into validated transaction rows.

    Args:
        content: UTF-8 CSV text with header row.

    Returns:
        Tuple of (valid_rows, errors). Each error includes the 1-based row number.
    """
    rows: list[BulkTransactionRow] = []
    errors: list[BulkTransactionError] = []

    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        errors.append(BulkTransactionError(row=0, error="CSV file is empty or has no header row"))
        return rows, errors

    # Normalize headers to lowercase
    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        errors.append(
            BulkTransactionError(
                row=0,
                error=f"Missing required columns: {', '.join(sorted(missing))}",
            )
        )
        return rows, errors

    for i, raw_row in enumerate(reader, start=2):  # row 1 is header
        if i - 1 > MAX_ROWS:
            errors.append(
                BulkTransactionError(
                    row=i,
                    error=f"Exceeds maximum of {MAX_ROWS} rows",
                )
            )
            break

        ticker = (raw_row.get("ticker") or "").strip().upper()
        if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker):
            errors.append(
                BulkTransactionError(row=i, ticker=ticker or None, error="Invalid ticker format")
            )
            continue

        txn_type = (raw_row.get("transaction_type") or "").strip().upper()
        if txn_type not in ("BUY", "SELL"):
            errors.append(
                BulkTransactionError(
                    row=i, ticker=ticker, error="transaction_type must be BUY or SELL"
                )
            )
            continue

        try:
            shares = Decimal(raw_row.get("shares", "").strip())
            if shares <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            errors.append(
                BulkTransactionError(row=i, ticker=ticker, error="shares must be a positive number")
            )
            continue

        try:
            price = Decimal(raw_row.get("price_per_share", "").strip())
            if price <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            errors.append(
                BulkTransactionError(
                    row=i, ticker=ticker, error="price_per_share must be a positive number"
                )
            )
            continue

        try:
            transacted_at = datetime.fromisoformat(raw_row.get("transacted_at", "").strip())
        except (ValueError, TypeError):
            errors.append(
                BulkTransactionError(
                    row=i, ticker=ticker, error="transacted_at must be ISO 8601 format"
                )
            )
            continue

        notes = (raw_row.get("notes") or "").strip() or None

        rows.append(
            BulkTransactionRow(
                ticker=ticker,
                transaction_type=txn_type,
                shares=shares,
                price_per_share=price,
                transacted_at=transacted_at,
                notes=notes,
            )
        )

    return rows, errors


async def ingest_new_tickers(
    rows: list[BulkTransactionRow],
    db: AsyncSession,
    user_id: str,
) -> list[BulkTransactionError]:
    """Ingest any tickers not yet in the DB, with bounded concurrency.

    Args:
        rows: Validated transaction rows.
        db: Async database session.
        user_id: Current user ID string.

    Returns:
        List of errors for tickers that failed to ingest.
    """
    # Find unique tickers that need ingest
    unique_tickers = {r.ticker for r in rows}
    result = await db.execute(select(Stock.ticker).where(Stock.ticker.in_(unique_tickers)))
    existing = {row[0] for row in result.all()}
    new_tickers = unique_tickers - existing

    if not new_tickers:
        return []

    from backend.services.ingest_lock import acquire_ingest_lock, release_ingest_lock
    from backend.services.pipelines import ingest_ticker

    errors: list[BulkTransactionError] = []
    sem = asyncio.Semaphore(INGEST_CONCURRENCY)

    async def _ingest_one(ticker: str) -> None:
        """Ingest a single ticker with lock acquisition and bounded concurrency."""
        async with sem:
            if not await acquire_ingest_lock(ticker):
                return  # another request is ingesting — skip, not an error
            try:
                await ingest_ticker(ticker, db, user_id=user_id)
            except Exception:
                logger.warning("Bulk ingest failed for %s", ticker, exc_info=True)
                errors.append(
                    BulkTransactionError(
                        row=0,
                        ticker=ticker,
                        error="Failed to fetch data for this ticker",
                    )
                )
            finally:
                await release_ingest_lock(ticker)

    await asyncio.gather(*[_ingest_one(t) for t in new_tickers])
    return errors
