"""Sync stock index memberships (S&P 500, NASDAQ-100, Dow 30) into the database.

Creates StockIndex records and populates StockIndexMembership by scraping
Wikipedia for constituent lists. Requires stocks to already exist in the
stocks table (run sync_sp500.py + seed_prices.py first for best results).

Usage:
    uv run python -m scripts.sync_indexes
    uv run python -m scripts.sync_indexes --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from io import StringIO

import pandas as pd
import requests
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import async_session_factory
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.stock import Stock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# Wikipedia URLs for index constituent tables
INDEX_SOURCES = {
    "sp500": {
        "name": "S&P 500",
        "description": "Standard & Poor's 500 — 500 large-cap US stocks",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "table_index": 0,
        "ticker_column": "Symbol",
    },
    "nasdaq100": {
        "name": "NASDAQ-100",
        "description": "100 largest non-financial companies on NASDAQ",
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "table_index": 4,
        "ticker_column": "Ticker",
    },
    "dow30": {
        "name": "Dow 30",
        "description": "Dow Jones Industrial Average — 30 blue-chip US stocks",
        "url": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        "table_index": 1,
        "ticker_column": "Symbol",
    },
}


def fetch_index_tickers(slug: str) -> list[str]:
    """Scrape tickers for a given index from Wikipedia.

    Args:
        slug: Index slug key from INDEX_SOURCES.

    Returns:
        List of ticker symbols (cleaned, dot-to-dash converted).
    """
    source = INDEX_SOURCES[slug]
    logger.info("Fetching %s constituents from Wikipedia...", source["name"])

    resp = requests.get(
        source["url"],
        headers={"User-Agent": "Mozilla/5.0 (compatible; StockSignalPlatform/1.0)"},
        timeout=15,
    )
    resp.raise_for_status()
    # html.parser has no XXE risk; input is from known Wikipedia pages
    tables = pd.read_html(  # nosemgrep: trailofbits.python.lxml-in-pandas.lxml-in-pandas
        StringIO(resp.text), flavor="html.parser"
    )
    df = tables[source["table_index"]]

    tickers = df[source["ticker_column"]].str.replace(".", "-", regex=False).str.strip().tolist()

    logger.info("Found %d tickers for %s", len(tickers), source["name"])
    return tickers


async def sync_indexes(dry_run: bool = False) -> dict[str, int]:
    """Create index records and populate memberships.

    Args:
        dry_run: If True, log what would happen without writing.

    Returns:
        Dict with counts per index: {"sp500": N, "nasdaq100": N, "dow30": N}.
    """
    counts: dict[str, int] = {}

    for slug, source in INDEX_SOURCES.items():
        try:
            tickers = fetch_index_tickers(slug)
        except Exception:
            logger.exception("Failed to fetch %s tickers", source["name"])
            counts[slug] = 0
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would sync %d tickers for %s",
                len(tickers),
                source["name"],
            )
            counts[slug] = len(tickers)
            continue

        async with async_session_factory() as db:
            # Upsert the index record
            idx_stmt = pg_insert(StockIndex).values(
                name=source["name"],
                slug=slug,
                description=source["description"],
            )
            idx_stmt = idx_stmt.on_conflict_do_update(
                index_elements=["slug"],
                set_={"name": idx_stmt.excluded.name},
            )
            await db.execute(idx_stmt)

            # Get the index ID
            result = await db.execute(select(StockIndex).where(StockIndex.slug == slug))
            index = result.scalar_one()

            # Get existing stock tickers in our DB
            stock_result = await db.execute(select(Stock.ticker))
            existing_tickers = {row[0] for row in stock_result.all()}

            # Upsert memberships (only for tickers that exist in our stocks table)
            linked = 0
            skipped = 0
            for ticker in tickers:
                if ticker not in existing_tickers:
                    skipped += 1
                    continue

                mem_stmt = pg_insert(StockIndexMembership).values(
                    ticker=ticker,
                    index_id=index.id,
                )
                mem_stmt = mem_stmt.on_conflict_do_nothing(
                    constraint="uq_ticker_index",
                )
                await db.execute(mem_stmt)
                linked += 1

            await db.commit()

            logger.info(
                "%s: linked %d stocks, skipped %d (not in DB)",
                source["name"],
                linked,
                skipped,
            )
            counts[slug] = linked

    return counts


async def main(dry_run: bool = False) -> None:
    """Entry point: sync all index memberships."""
    counts = await sync_indexes(dry_run=dry_run)
    total = sum(counts.values())
    logger.info(
        "Index sync complete: %s (total %d memberships)",
        ", ".join(f"{k}={v}" for k, v in counts.items()),
        total,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync stock index memberships to database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
