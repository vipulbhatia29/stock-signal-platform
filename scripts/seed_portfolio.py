"""Seed a user account, portfolio, positions, and watchlist from a Fidelity CSV export.

Usage:
    uv run python -m scripts.seed_portfolio --csv /path/to/positions.csv \
        --email user@example.com --password Password123
"""

import argparse
import asyncio
import csv
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select, text

from backend.database import async_session_factory
from backend.dependencies import hash_password
from backend.models.portfolio import Portfolio, Position
from backend.models.stock import Stock, Watchlist
from backend.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


def _parse_decimal(val: str) -> Decimal | None:
    """Parse a decimal value, stripping $, commas, and whitespace."""
    if not val or val in ("--", "N/A", "Incomplete"):
        return None
    cleaned = val.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def parse_fidelity_csv(csv_path: str) -> list[dict]:
    """Parse a Fidelity positions CSV into a list of position dicts."""
    positions = []
    with open(csv_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Skip the account header line (line 1) and blank line (line 2)
    # CSV header is on line 3 (index 2)
    reader = csv.DictReader(lines[2:])
    for row in reader:
        symbol = row.get("Symbol", "").strip()
        asset_type = row.get("Asset Type", "").strip()

        # Skip non-equity rows (ETFs, cash, totals)
        if asset_type != "Equity":
            continue
        if not symbol or symbol in ("Cash & Cash Investments", "Positions Total"):
            continue

        shares = _parse_decimal(row.get("Qty (Quantity)", ""))
        cost_basis = _parse_decimal(row.get("Cost Basis", ""))
        price = _parse_decimal(row.get("Price", ""))
        description = row.get("Description", "").strip()

        if shares is None or shares <= 0:
            logger.warning("Skipping %s: invalid shares", symbol)
            continue

        # If cost basis missing, estimate from price
        if cost_basis is None or cost_basis <= 0:
            if price and price > 0:
                cost_basis = price * shares
            else:
                logger.warning("Skipping %s: no cost basis or price", symbol)
                continue

        avg_cost = cost_basis / shares

        positions.append(
            {
                "ticker": symbol,
                "description": description,
                "shares": shares,
                "avg_cost_basis": avg_cost,
                "price": price,
            }
        )

    return positions


async def seed(csv_path: str, email: str, password: str) -> None:
    """Create user, portfolio, positions, and watchlist from CSV."""
    positions_data = parse_fidelity_csv(csv_path)
    logger.info("Parsed %d equity positions from CSV", len(positions_data))

    async with async_session_factory() as db:
        # 1. Check/create user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            logger.info("User %s already exists (id=%s)", email, user.id)
        else:
            user = User(
                email=email,
                hashed_password=hash_password(password),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.flush()
            logger.info("Created user %s (id=%s)", email, user.id)

        # 2. Check/create portfolio
        result = await db.execute(select(Portfolio).where(Portfolio.user_id == user.id))
        portfolio = result.scalar_one_or_none()
        if portfolio:
            logger.info("Portfolio already exists (id=%s)", portfolio.id)
        else:
            portfolio = Portfolio(
                user_id=user.id,
                name="Fidelity Brokerage",
                description="Imported from Fidelity CSV export",
            )
            db.add(portfolio)
            await db.flush()
            logger.info("Created portfolio '%s' (id=%s)", portfolio.name, portfolio.id)

        # 3. Ensure all tickers exist in stocks table
        tickers_needed = {p["ticker"] for p in positions_data}
        result = await db.execute(select(Stock.ticker).where(Stock.ticker.in_(tickers_needed)))
        existing_tickers = {r[0] for r in result.fetchall()}
        missing_tickers = tickers_needed - existing_tickers

        if missing_tickers:
            logger.info("Creating %d missing stock records", len(missing_tickers))
            ticker_to_desc = {p["ticker"]: p["description"] for p in positions_data}
            for ticker in sorted(missing_tickers):
                stock = Stock(
                    ticker=ticker,
                    name=ticker_to_desc.get(ticker, ticker),
                    is_active=True,
                )
                db.add(stock)
            await db.flush()
            logger.info("Created stocks: %s", sorted(missing_tickers))

        # 4. Upsert positions
        created = 0
        updated = 0
        now = datetime.now(timezone.utc)

        for pos_data in positions_data:
            result = await db.execute(
                select(Position).where(
                    Position.portfolio_id == portfolio.id,
                    Position.ticker == pos_data["ticker"],
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.shares = pos_data["shares"]
                existing.avg_cost_basis = pos_data["avg_cost_basis"]
                updated += 1
            else:
                position = Position(
                    portfolio_id=portfolio.id,
                    ticker=pos_data["ticker"],
                    shares=pos_data["shares"],
                    avg_cost_basis=pos_data["avg_cost_basis"],
                    opened_at=now,
                )
                db.add(position)
                created += 1

        logger.info("Positions: %d created, %d updated", created, updated)

        # 5. Add all positions to watchlist
        result = await db.execute(select(Watchlist.ticker).where(Watchlist.user_id == user.id))
        existing_watchlist = {r[0] for r in result.fetchall()}
        wl_added = 0

        for pos_data in positions_data:
            if pos_data["ticker"] not in existing_watchlist:
                wl = Watchlist(
                    user_id=user.id,
                    ticker=pos_data["ticker"],
                )
                db.add(wl)
                wl_added += 1

        logger.info("Watchlist: %d new entries added", wl_added)

        await db.commit()
        logger.info("Seed complete!")

        # Summary
        result = await db.execute(
            text("SELECT COUNT(*) FROM positions WHERE portfolio_id = :pid"),
            {"pid": str(portfolio.id)},
        )
        total_positions = result.scalar()
        result = await db.execute(
            text("SELECT COUNT(*) FROM watchlist WHERE user_id = :uid"),
            {"uid": str(user.id)},
        )
        total_watchlist = result.scalar()
        logger.info(
            "Summary: user=%s, portfolio=%s, positions=%d, watchlist=%d",
            email,
            portfolio.name,
            total_positions,
            total_watchlist,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed portfolio from Fidelity CSV")
    parser.add_argument("--csv", required=True, help="Path to Fidelity positions CSV")
    parser.add_argument("--email", default="vipul@example.com", help="User email")
    parser.add_argument("--password", default="TestPass123!", help="User password")
    args = parser.parse_args()

    if not Path(args.csv).exists():
        parser.error(f"CSV file not found: {args.csv}")

    asyncio.run(seed(args.csv, args.email, args.password))


if __name__ == "__main__":
    main()
