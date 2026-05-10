"""Snapshot import service — store CSV snapshots, diff, sync positions.

Core flow:
1. Dedup check (csv_hash)
2. Baseline bootstrap (first import)
3. Store snapshot rows
4. Compute diffs against previous snapshot
5. Best-effort Position table sync
6. Watchlist sync
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.attribution import PositionChange, PositionSnapshot
from backend.models.portfolio import Position
from backend.models.stock import Stock, Watchlist
from backend.schemas.attribution import ImportResult, ImportWarning, SnapshotRowSchema
from backend.services.stock_data import ensure_stock_exists

logger = logging.getLogger(__name__)


def compute_csv_hash(content: str) -> str:
    """SHA-256 hash of raw CSV content for dedup."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _classify_action(*, prev: Decimal, new: Decimal) -> str | None:
    """Derive implied action from share delta.

    Returns None if shares are unchanged.
    """
    if prev == 0 and new > 0:
        return "OPEN"
    if prev > 0 and new > prev:
        return "ADD"
    if prev > 0 and new < prev and new > 0:
        return "TRIM"
    if prev > 0 and new == 0:
        return "CLOSE"
    return None


def _compute_diffs(
    prev: dict[str, tuple[Decimal, Decimal]],
    curr: dict[str, tuple[Decimal, Decimal]],
) -> list[dict]:
    """Compute position diffs between two snapshot states.

    Args:
        prev: {ticker: (shares, avg_cost)} from previous snapshot.
        curr: {ticker: (shares, avg_cost)} from current snapshot.

    Returns:
        List of diff dicts with keys: ticker, prev_shares, new_shares,
        delta_shares, prev_avg_cost_basis, new_avg_cost_basis, implied_action.
    """
    diffs: list[dict] = []
    all_tickers = set(prev) | set(curr)

    for ticker in sorted(all_tickers):
        prev_shares, prev_cost = prev.get(ticker, (Decimal("0"), Decimal("0")))
        new_shares, new_cost = curr.get(ticker, (Decimal("0"), Decimal("0")))

        action = _classify_action(prev=prev_shares, new=new_shares)
        if action is None:
            continue

        diffs.append(
            {
                "ticker": ticker,
                "prev_shares": prev_shares,
                "new_shares": new_shares,
                "delta_shares": new_shares - prev_shares,
                "prev_avg_cost_basis": prev_cost,
                "new_avg_cost_basis": new_cost,
                "implied_action": action,
            }
        )

    return diffs


async def _get_previous_snapshot(
    portfolio_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, tuple[Decimal, Decimal, uuid.UUID]]:
    """Load most recent snapshot for each ticker.

    Returns: {ticker: (shares, avg_cost, snapshot_id)}
    """
    # Find the most recent imported_at for this portfolio
    latest_q = (
        select(PositionSnapshot.imported_at)
        .where(PositionSnapshot.portfolio_id == portfolio_id)
        .order_by(PositionSnapshot.imported_at.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_q)
    latest_at = latest_result.scalar_one_or_none()

    if latest_at is None:
        return {}

    rows_q = select(PositionSnapshot).where(
        PositionSnapshot.portfolio_id == portfolio_id,
        PositionSnapshot.imported_at == latest_at,
    )
    rows_result = await db.execute(rows_q)
    rows = rows_result.scalars().all()

    return {r.ticker: (r.shares, r.avg_cost_basis, r.id) for r in rows}


async def _create_baseline_from_positions(
    portfolio_id: uuid.UUID,
    csv_hash: str,
    db: AsyncSession,
) -> bool:
    """Generate baseline snapshot from existing Position table state.

    Called on first import when positions already exist (from seed).
    Returns True if baseline was created.
    """
    result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.shares > 0,
        )
    )
    positions = result.scalars().all()

    if not positions:
        return False

    now = datetime.now(timezone.utc)
    for pos in positions:
        snap = PositionSnapshot(
            portfolio_id=portfolio_id,
            ticker=pos.ticker,
            imported_at=now,
            shares=pos.shares,
            avg_cost_basis=pos.avg_cost_basis,
            csv_hash=f"baseline_{csv_hash}",
            is_baseline=True,
        )
        db.add(snap)

    await db.flush()
    logger.info(
        "Created baseline snapshot from %d existing positions for portfolio %s",
        len(positions),
        portfolio_id,
    )
    return True


async def _sync_positions(
    portfolio_id: uuid.UUID,
    rows: list[SnapshotRowSchema],
    db: AsyncSession,
) -> None:
    """Best-effort Position table sync from CSV state.

    Upserts positions to match CSV. This is a display convenience —
    attribution uses position_snapshots as source of truth.
    """
    now = datetime.now(timezone.utc)
    current_tickers = {r.ticker for r in rows}

    if rows:
        values_list = [
            {
                "id": uuid.uuid4(),
                "portfolio_id": portfolio_id,
                "ticker": row.ticker,
                "shares": row.shares,
                "avg_cost_basis": row.avg_cost_basis,
                "opened_at": now,
                "created_at": now,
                "updated_at": now,
            }
            for row in rows
        ]
        stmt = pg_insert(Position.__table__).values(values_list)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_positions_portfolio_ticker",
            set_={
                "shares": stmt.excluded.shares,
                "avg_cost_basis": stmt.excluded.avg_cost_basis,
                "updated_at": now,
                "closed_at": None,
            },
        )
        await db.execute(stmt)

    # Close positions not in CSV
    close_result = await db.execute(
        select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.ticker.notin_(current_tickers),
            Position.closed_at.is_(None),
        )
    )
    for pos in close_result.scalars().all():
        pos.closed_at = now
        pos.shares = Decimal("0")

    await db.flush()


async def _sync_watchlist(
    user_id: uuid.UUID,
    tickers: set[str],
    db: AsyncSession,
) -> None:
    """Add imported tickers to user's watchlist. Skip existing."""
    result = await db.execute(select(Watchlist.ticker).where(Watchlist.user_id == user_id))
    existing = {row[0] for row in result.all()}

    for ticker in tickers - existing:
        db.add(Watchlist(user_id=user_id, ticker=ticker))

    await db.flush()


async def import_portfolio_snapshot(
    portfolio_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[SnapshotRowSchema],
    csv_hash: str,
    db: AsyncSession,
) -> ImportResult:
    """Import a parsed CSV snapshot into the database.

    Stores snapshot rows, computes diffs against previous snapshot,
    syncs Position table, and syncs watchlist.

    Args:
        portfolio_id: The user's portfolio ID.
        user_id: The authenticated user's ID.
        rows: Parsed and validated snapshot rows.
        csv_hash: SHA-256 of raw CSV content for dedup.
        db: Async SQLAlchemy session.

    Returns:
        ImportResult with counts and warnings.
    """
    warnings: list[ImportWarning] = []

    # 1. Dedup check
    existing = await db.execute(
        select(PositionSnapshot.imported_at)
        .where(
            PositionSnapshot.portfolio_id == portfolio_id,
            PositionSnapshot.csv_hash == csv_hash,
        )
        .limit(1)
    )
    dup_date = existing.scalar_one_or_none()
    if dup_date is not None:
        return ImportResult(
            imported=0,
            is_duplicate=True,
        )

    # 2. Baseline check
    prev_snapshot = await _get_previous_snapshot(portfolio_id, db)
    is_baseline = False

    if not prev_snapshot:
        # No prior snapshots — check if positions exist from seed
        created = await _create_baseline_from_positions(portfolio_id, csv_hash, db)
        if created:
            # Re-load the baseline we just created
            prev_snapshot = await _get_previous_snapshot(portfolio_id, db)
        else:
            is_baseline = True

    # 3. Auto-create stocks for unknown tickers (batch pre-check + targeted create)
    # First, batch-check which tickers already exist to avoid N+1 queries.
    # Then only call ensure_stock_exists for the missing ones.
    all_tickers = {row.ticker for row in rows}
    existing_result = await db.execute(select(Stock.ticker).where(Stock.ticker.in_(all_tickers)))
    existing_tickers = {row[0] for row in existing_result.all()}
    missing_tickers = all_tickers - existing_tickers

    failed_tickers: set[str] = set()
    for ticker in missing_tickers:
        try:
            await ensure_stock_exists(ticker, db)
        except ValueError:
            failed_tickers.add(ticker)
            warnings.append(
                ImportWarning(
                    message=f"{ticker} not found — skipped. Is this a mutual fund?",
                )
            )

    # Filter to tickers that have a valid stock record
    valid_rows = [r for r in rows if r.ticker not in failed_tickers]

    # 4. Store snapshot
    now = datetime.now(timezone.utc)
    snapshot_map: dict[str, uuid.UUID] = {}

    for row in valid_rows:
        snap_id = uuid.uuid4()
        snap = PositionSnapshot(
            id=snap_id,
            portfolio_id=portfolio_id,
            ticker=row.ticker,
            imported_at=now,
            shares=row.shares,
            avg_cost_basis=row.avg_cost_basis,
            market_value=row.market_value,
            current_price=row.price,
            asset_type=row.asset_type,
            csv_hash=csv_hash,
            is_baseline=is_baseline,
        )
        db.add(snap)
        snapshot_map[row.ticker] = snap_id

    await db.flush()

    # 5. Compute diffs (skip if baseline)
    changes_detected = 0
    if not is_baseline and prev_snapshot:
        prev_state = {
            ticker: (shares, cost) for ticker, (shares, cost, _sid) in prev_snapshot.items()
        }
        curr_state = {row.ticker: (row.shares, row.avg_cost_basis) for row in valid_rows}
        diffs = _compute_diffs(prev_state, curr_state)

        for diff in diffs:
            ticker = diff["ticker"]
            before_id = (
                prev_snapshot.get(ticker, (None, None, None))[2]
                if ticker in prev_snapshot
                else None
            )
            after_id = snapshot_map.get(ticker)

            # For CLOSE, the ticker isn't in curr snapshot — no after_id
            if after_id is None and diff["implied_action"] == "CLOSE":
                # Create a zero-share snapshot row for the close
                close_id = uuid.uuid4()
                close_snap = PositionSnapshot(
                    id=close_id,
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    imported_at=now,
                    shares=Decimal("0"),
                    avg_cost_basis=Decimal("0"),
                    csv_hash=csv_hash,
                    is_baseline=False,
                )
                db.add(close_snap)
                after_id = close_id

            if after_id is None:
                continue  # Unknown ticker — skip

            change = PositionChange(
                portfolio_id=portfolio_id,
                ticker=ticker,
                detected_at=now,
                snapshot_before_id=before_id,
                snapshot_after_id=after_id,
                prev_shares=diff["prev_shares"],
                new_shares=diff["new_shares"],
                delta_shares=diff["delta_shares"],
                prev_avg_cost_basis=diff["prev_avg_cost_basis"],
                new_avg_cost_basis=diff["new_avg_cost_basis"],
                implied_action=diff["implied_action"],
                attribution_status="pending",
            )
            db.add(change)
            changes_detected += 1

        await db.flush()

    # 6. Sync Position table
    await _sync_positions(portfolio_id, valid_rows, db)

    # 7. Sync Watchlist
    await _sync_watchlist(user_id, {r.ticker for r in valid_rows}, db)

    await db.commit()

    logger.info(
        "Imported %d positions for portfolio %s (%d changes detected, baseline=%s)",
        len(valid_rows),
        portfolio_id,
        changes_detected,
        is_baseline,
    )

    return ImportResult(
        imported=len(valid_rows),
        warnings=warnings,
        changes_detected=changes_detected,
        is_baseline=is_baseline,
    )
