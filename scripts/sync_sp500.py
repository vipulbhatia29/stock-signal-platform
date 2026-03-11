"""Sync S&P 500 stock universe into the stocks table.

Fetches the current S&P 500 constituents from Wikipedia and upserts them
into the database. Stocks already in the table are updated with latest
sector/industry info; new stocks are inserted.

Usage:
    uv run python -m scripts.sync_sp500
    uv run python -m scripts.sync_sp500 --dry-run   # preview without writing
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import async_session_factory
from backend.models.stock import Stock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# Wikipedia URL for the S&P 500 constituents table
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_sp500_tickers() -> pd.DataFrame:
    """Scrape the S&P 500 constituents table from Wikipedia.

    Returns:
        DataFrame with columns: ticker, name, sector, industry, exchange.
    """
    tables = pd.read_html(SP500_URL)
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
    """Upsert S&P 500 stocks into the database.

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
        # Get existing tickers to distinguish inserts vs updates
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
                "is_in_universe": True,
                "is_active": True,
            }

            stmt = pg_insert(Stock).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "name": stmt.excluded.name,
                    "sector": stmt.excluded.sector,
                    "industry": stmt.excluded.industry,
                    "is_in_universe": True,
                    "is_active": True,
                },
            )
            await db.execute(stmt)

            if row["ticker"] in existing_tickers:
                updated += 1
            else:
                inserted += 1

        # Mark stocks no longer in S&P 500 as not in universe
        sp500_tickers = set(df["ticker"].tolist())
        stale_stmt = (
            update(Stock)
            .where(Stock.is_in_universe.is_(True))
            .where(Stock.ticker.notin_(sp500_tickers))
            .values(is_in_universe=False)
        )
        stale_result = await db.execute(stale_stmt)
        stale_count = stale_result.rowcount

        await db.commit()

        if stale_count > 0:
            logger.info("Marked %d stocks as no longer in S&P 500", stale_count)

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
