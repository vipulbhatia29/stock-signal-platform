"""Sync S&P 500 stock universe into the stocks and stock_index_membership tables.

Fetches the current S&P 500 constituents from Wikipedia and upserts them
into the database. Stock records are created/updated in the stocks table;
index membership is tracked in stock_index_membership (linked to the
"S&P 500" StockIndex record).

Usage:
    uv run python -m scripts.sync_sp500
    uv run python -m scripts.sync_sp500 --dry-run   # preview without writing
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import async_session_factory
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.stock import Stock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# Wikipedia URL for the S&P 500 constituents table
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Canonical slug for the S&P 500 index
SP500_SLUG = "sp500"
SP500_NAME = "S&P 500"


def fetch_sp500_tickers() -> pd.DataFrame:
    """Scrape the S&P 500 constituents table from Wikipedia.

    Returns:
        DataFrame with columns: ticker, name, sector, industry, exchange.
    """
    resp = requests.get(
        SP500_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; StockSignalPlatform/1.0)"},
        timeout=15,
    )
    resp.raise_for_status()
    # lxml HTML parser is safe here — pd.read_html uses lxml.html (no XXE risk)
    tables = pd.read_html(  # nosemgrep: trailofbits.python.lxml-in-pandas.lxml-in-pandas
        StringIO(resp.text), flavor="lxml"
    )
    # The first table on the page is the current constituents
    df = tables[0]

    # Standardize column names
    result = pd.DataFrame(
        {
            "ticker": df["Symbol"].str.replace(".", "-", regex=False).str.strip(),
            "name": df["Security"].str.strip(),
            "sector": df["GICS Sector"].str.strip(),
            "industry": df["GICS Sub-Industry"].str.strip(),
        }
    )
    # Wikipedia doesn't list exchange, but all S&P 500 are NYSE or NASDAQ
    result["exchange"] = None

    return result


async def sync_stocks(df: pd.DataFrame, dry_run: bool = False) -> dict[str, int]:
    """Upsert S&P 500 stocks and sync index membership into the database.

    Args:
        df: DataFrame from fetch_sp500_tickers().
        dry_run: If True, log what would happen without writing.

    Returns:
        Dict with counts: {"inserted": N, "updated": N, "total": N}.
    """
    if dry_run:
        logger.info("[DRY RUN] Would sync %d stocks", len(df))
        for _, row in df.head(10).iterrows():
            logger.info("  %s — %s (%s)", row["ticker"], row["name"], row["sector"])
        if len(df) > 10:
            logger.info("  ... and %d more", len(df) - 10)
        return {"inserted": 0, "updated": 0, "total": len(df)}

    async with async_session_factory() as db:
        # ── Ensure the S&P 500 index record exists ───────────────────
        idx_result = await db.execute(select(StockIndex).where(StockIndex.slug == SP500_SLUG))
        sp500_index = idx_result.scalar_one_or_none()
        if sp500_index is None:
            sp500_index = StockIndex(
                name=SP500_NAME,
                slug=SP500_SLUG,
                description="S&P 500 index constituents",
            )
            db.add(sp500_index)
            await db.flush()  # populate id without committing
            logger.info("Created StockIndex record for %s", SP500_NAME)

        # ── Get existing tickers to distinguish inserts vs updates ───
        result = await db.execute(select(Stock.ticker))
        existing_tickers = {row[0] for row in result.all()}

        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            values = {
                "ticker": row["ticker"],
                "name": row["name"],
                "sector": row["sector"],
                "industry": row["industry"],
                "exchange": row["exchange"],
                "is_active": True,
            }

            stmt = pg_insert(Stock).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "name": stmt.excluded.name,
                    "sector": stmt.excluded.sector,
                    "industry": stmt.excluded.industry,
                    "is_active": True,
                },
            )
            await db.execute(stmt)

            if row["ticker"] in existing_tickers:
                updated += 1
            else:
                inserted += 1

        # ── Sync index membership ────────────────────────────────────
        now = datetime.now(timezone.utc)
        sp500_tickers = set(df["ticker"].tolist())

        # Upsert current memberships (re-add if previously removed)
        for ticker in sp500_tickers:
            membership_stmt = (
                pg_insert(StockIndexMembership)
                .values(
                    ticker=ticker,
                    index_id=sp500_index.id,
                    added_at=now,
                    removed_date=None,
                )
                .on_conflict_do_update(
                    constraint="uq_ticker_index",
                    set_={"removed_date": None},  # re-add if previously removed
                )
            )
            await db.execute(membership_stmt)

        # Mark stale memberships (tickers no longer in S&P 500) as removed
        stale_stmt = (
            update(StockIndexMembership)
            .where(StockIndexMembership.index_id == sp500_index.id)
            .where(StockIndexMembership.ticker.notin_(sp500_tickers))
            .where(StockIndexMembership.removed_date.is_(None))
            .values(removed_date=now)
        )
        stale_result = await db.execute(stale_stmt)
        stale_count = stale_result.rowcount
        if stale_count > 0:
            logger.info("Marked %d stale S&P 500 membership records as removed", stale_count)

        # Update last_synced_at on the index record
        sp500_index.last_synced_at = now

        await db.commit()

        return {"inserted": inserted, "updated": updated, "total": len(df)}


async def main(dry_run: bool = False) -> None:
    """Entry point: fetch S&P 500 list and sync to database."""
    logger.info("Fetching S&P 500 constituents from Wikipedia...")
    df = fetch_sp500_tickers()
    logger.info("Found %d tickers", len(df))

    counts = await sync_stocks(df, dry_run=dry_run)
    logger.info(
        "Sync complete: %d inserted, %d updated, %d total",
        counts["inserted"],
        counts["updated"],
        counts["total"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync S&P 500 stocks to database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
