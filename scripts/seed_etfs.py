"""Seed ETF tickers (11 SPDR sector ETFs + SPY) into the stocks table.

Marks each as is_etf=True, fetches 10 years of historical prices, and stores
them in stock_prices. Idempotent — skips tickers that already exist.

The 10-year window matches ``scripts/seed_prices.py`` so QuantStats
benchmarking (alpha, beta, Sharpe vs SPY) has a full SPY history to
compare stock returns against. See KAN-406.

Usage:
    uv run python -m scripts.seed_etfs
"""

import asyncio
import logging
import time

import yfinance as yf
from sqlalchemy import select

from backend.database import async_session_factory
from backend.models.price import StockPrice
from backend.models.stock import Stock

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RATE_LIMIT_SECONDS = 0.5

# 11 SPDR Select Sector ETFs + SPY benchmark
ETF_UNIVERSE: list[dict[str, str]] = [
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "Broad Market"},
    {"ticker": "XLK", "name": "Technology Select Sector SPDR Fund", "sector": "Technology"},
    {"ticker": "XLV", "name": "Health Care Select Sector SPDR Fund", "sector": "Healthcare"},
    {"ticker": "XLF", "name": "Financial Select Sector SPDR Fund", "sector": "Financials"},
    {
        "ticker": "XLY",
        "name": "Consumer Discretionary Select Sector SPDR Fund",
        "sector": "Consumer Discretionary",
    },
    {
        "ticker": "XLP",
        "name": "Consumer Staples Select Sector SPDR Fund",
        "sector": "Consumer Staples",
    },
    {"ticker": "XLE", "name": "Energy Select Sector SPDR Fund", "sector": "Energy"},
    {"ticker": "XLI", "name": "Industrial Select Sector SPDR Fund", "sector": "Industrials"},
    {"ticker": "XLB", "name": "Materials Select Sector SPDR Fund", "sector": "Materials"},
    {"ticker": "XLU", "name": "Utilities Select Sector SPDR Fund", "sector": "Utilities"},
    {"ticker": "XLRE", "name": "Real Estate Select Sector SPDR Fund", "sector": "Real Estate"},
    {
        "ticker": "XLC",
        "name": "Communication Services Select Sector SPDR Fund",
        "sector": "Communication Services",
    },
]


async def seed_etf(etf: dict[str, str]) -> dict[str, str | int]:
    """Seed a single ETF: create Stock row + fetch 10y prices.

    Args:
        etf: Dict with ticker, name, sector keys.

    Returns:
        Summary dict with ticker, status, and row count.
    """
    ticker = etf["ticker"]
    result: dict[str, str | int] = {"ticker": ticker, "status": "ok"}

    async with async_session_factory() as db:
        # Check if ticker already exists
        existing = await db.execute(select(Stock).where(Stock.ticker == ticker))
        stock = existing.scalar_one_or_none()

        if stock is None:
            stock = Stock(
                ticker=ticker,
                name=etf["name"],
                sector=etf["sector"],
                exchange="NYSE Arca",
                is_etf=True,
                is_active=True,
            )
            db.add(stock)
            await db.flush()
            logger.info("Created Stock row for %s", ticker)
        elif not stock.is_etf:
            stock.is_etf = True
            await db.flush()
            logger.info("Marked existing %s as ETF", ticker)
        else:
            logger.info("Stock %s already exists as ETF, skipping creation", ticker)

        # Fetch 10 years of historical prices (matches seed_prices.py for
        # QuantStats benchmarking — see KAN-406).
        try:
            yf_ticker = yf.Ticker(ticker)
            df = yf_ticker.history(period="10y")

            if df.empty:
                logger.warning("No price data returned for %s", ticker)
                result["status"] = "no_data"
                result["price_rows"] = 0
                await db.commit()
                return result

            rows_added = 0
            for idx, row in df.iterrows():
                price = StockPrice(
                    ticker=ticker,
                    time=idx.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    adj_close=float(row["Close"]),
                    volume=int(row["Volume"]),
                    source="yfinance",
                )
                await db.merge(price)
                rows_added += 1

            await db.commit()
            result["price_rows"] = rows_added
            logger.info("Stored %d price rows for %s", rows_added, ticker)

        except Exception as e:
            logger.error("Failed to fetch prices for %s: %s", ticker, e)
            result["status"] = "error"
            result["error"] = str(e)
            await db.rollback()

    return result


async def main() -> None:
    """Seed all ETFs in the universe."""
    logger.info("Seeding %d ETFs...", len(ETF_UNIVERSE))
    results: list[dict[str, str | int]] = []

    for i, etf in enumerate(ETF_UNIVERSE, 1):
        logger.info("[%d/%d] Seeding %s...", i, len(ETF_UNIVERSE), etf["ticker"])
        start = time.time()

        result = await seed_etf(etf)
        elapsed = time.time() - start

        if result["status"] == "ok":
            logger.info(
                "[%d/%d] %s: %s price rows — %.1fs",
                i,
                len(ETF_UNIVERSE),
                etf["ticker"],
                result.get("price_rows", 0),
                elapsed,
            )
        else:
            logger.error(
                "[%d/%d] %s: %s — %.1fs",
                i,
                len(ETF_UNIVERSE),
                etf["ticker"],
                result.get("error", result["status"]),
                elapsed,
            )

        results.append(result)

        if i < len(ETF_UNIVERSE):
            await asyncio.sleep(RATE_LIMIT_SECONDS)

    ok_count = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] != "ok")
    logger.info("ETF seed complete: %d succeeded, %d failed", ok_count, err_count)


if __name__ == "__main__":
    asyncio.run(main())
