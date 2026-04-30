"""Backfill historical_features table from stock_prices.

Computes 11 technical indicators + forward return targets for all tickers
in the database. This creates the training dataset for the LightGBM+XGBoost
forecast ensemble.

Usage:
    # Backfill all tickers
    uv run python -m scripts.backfill_features

    # Backfill specific tickers
    uv run python -m scripts.backfill_features --tickers AAPL MSFT GOOGL

    # Dry run — show ticker count and estimated rows
    uv run python -m scripts.backfill_features --dry-run

    # Limit to last N trading days per ticker
    uv run python -m scripts.backfill_features --max-days 500
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.historical_feature import HistoricalFeature
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.services.feature_engineering import build_feature_dataframe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 1500  # rows per INSERT (21 cols × 1500 = 31500 params, under asyncpg 32767 limit)
SMA_WARMUP = 200  # rows needed before SMA-200 produces valid output


async def _load_all_prices(ticker: str, db: AsyncSession) -> pd.DataFrame | None:
    """Load all price data for a ticker from stock_prices.

    Args:
        ticker: Stock ticker symbol.
        db: Async database session.

    Returns:
        DataFrame with DatetimeIndex and adj_close column, or None if no data.
    """
    result = await db.execute(
        select(StockPrice.time, StockPrice.adj_close)
        .where(StockPrice.ticker == ticker)
        .order_by(StockPrice.time.asc())
    )
    rows = result.all()
    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["time", "adj_close"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    df["adj_close"] = df["adj_close"].astype(float)
    return df


async def _load_spy_closes(db: AsyncSession) -> pd.Series:
    """Load all SPY closing prices from stock_prices.

    Args:
        db: Async database session.

    Returns:
        Series of SPY adj_close with DatetimeIndex.
    """
    result = await db.execute(
        select(StockPrice.time, StockPrice.adj_close)
        .where(StockPrice.ticker == "SPY")
        .order_by(StockPrice.time.asc())
    )
    rows = result.all()
    if not rows:
        raise RuntimeError("No SPY data in stock_prices. Run seed_prices first.")

    df = pd.DataFrame(rows, columns=["time", "adj_close"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    return df["adj_close"].astype(float)


def _download_vix_history() -> pd.Series:
    """Download VIX closing prices from yfinance.

    Returns:
        Series of VIX close prices with DatetimeIndex (UTC).
    """
    logger.info("Downloading VIX history from yfinance...")
    vix = yf.download("^VIX", period="10y", progress=False)
    if vix.empty:
        raise RuntimeError("Failed to download VIX data from yfinance")
    # yfinance returns MultiIndex columns for single ticker: flatten
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
    closes = vix["Close"].copy()
    if closes.index.tz is None:
        closes.index = closes.index.tz_localize("UTC")
    logger.info("Downloaded %d VIX data points", len(closes))
    return closes


async def _get_all_tickers(db: AsyncSession) -> list[str]:
    """Get all tickers from the stocks table.

    Args:
        db: Async database session.

    Returns:
        Sorted list of ticker symbols.
    """
    result = await db.execute(select(Stock.ticker).order_by(Stock.ticker))
    return [row[0] for row in result.all()]


async def _bulk_upsert_features(
    features_df: pd.DataFrame,
    ticker: str,
    db: AsyncSession,
) -> int:
    """Bulk upsert feature rows for a ticker.

    Uses ON CONFLICT DO UPDATE to handle re-runs safely.

    Args:
        features_df: DataFrame from build_feature_dataframe().
        ticker: Ticker symbol.
        db: Async database session.

    Returns:
        Number of rows upserted.
    """
    if features_df.empty:
        return 0

    rows = []
    for idx, row in features_df.iterrows():
        dt = idx.date() if hasattr(idx, "date") else idx
        values = {
            "date": dt,
            "ticker": ticker,
            "momentum_21d": round(float(row["momentum_21d"]), 6),
            "momentum_63d": round(float(row["momentum_63d"]), 6),
            "momentum_126d": round(float(row["momentum_126d"]), 6),
            "rsi_value": round(float(row["rsi_value"]), 2),
            "macd_histogram": round(float(row["macd_histogram"]), 6),
            "sma_cross": int(row["sma_cross"]),
            "bb_position": int(row["bb_position"]),
            "volatility": round(float(row["volatility"]), 6),
            "sharpe_ratio": round(float(row["sharpe_ratio"]), 6),
            "vix_level": round(float(row["vix_level"]), 2),
            "spy_momentum_21d": round(float(row["spy_momentum_21d"]), 6),
            "stock_sentiment": None,
            "sector_sentiment": None,
            "macro_sentiment": None,
            "sentiment_confidence": None,
            "signals_aligned": None,
            "convergence_label": None,
            "forward_return_60d": (
                round(float(row["forward_return_60d"]), 6)
                if pd.notna(row["forward_return_60d"])
                else None
            ),
            "forward_return_90d": (
                round(float(row["forward_return_90d"]), 6)
                if pd.notna(row["forward_return_90d"])
                else None
            ),
        }
        rows.append(values)

    # Batch insert
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        stmt = pg_insert(HistoricalFeature).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "ticker"],
            set_={k: stmt.excluded[k] for k in batch[0] if k not in ("date", "ticker")},
        )
        await db.execute(stmt)
        total += len(batch)

    await db.commit()
    return total


async def run_backfill(
    tickers: list[str] | None = None,
    max_days: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the full backfill pipeline.

    Args:
        tickers: Optional list of tickers. None = all tickers.
        max_days: Optional limit on trading days per ticker.
        dry_run: If True, just log what would happen.

    Returns:
        Dict with counts: tickers_processed, total_rows, skipped, errors.
    """
    async with async_session_factory() as db:
        if tickers:
            ticker_list = [t.upper() for t in tickers]
        else:
            ticker_list = await _get_all_tickers(db)

    logger.info("Backfill targets: %d tickers", len(ticker_list))

    if dry_run:
        logger.info("DRY RUN — no data will be written")
        return {"tickers": len(ticker_list), "dry_run": True}

    # Download VIX + SPY after dry-run gate (avoid 30s download for dry runs)
    vix_closes = _download_vix_history()

    async with async_session_factory() as db:
        spy_closes = await _load_spy_closes(db)

    stats: dict = {"tickers_processed": 0, "total_rows": 0, "skipped": 0, "errors": []}
    start = time.monotonic()

    for i, ticker in enumerate(ticker_list, 1):
        try:
            async with async_session_factory() as db:
                price_df = await _load_all_prices(ticker, db)

            if price_df is None or len(price_df) < 200:
                logger.info(
                    "[%d/%d] %s — skipped (only %d price rows, need 200+)",
                    i,
                    len(ticker_list),
                    ticker,
                    len(price_df) if price_df is not None else 0,
                )
                stats["skipped"] += 1
                continue

            if max_days:
                # Load extra 200 rows for SMA-200 warmup, then keep last
                # max_days of *features* (warmup rows are dropped by
                # build_feature_dataframe anyway)
                load_rows = max_days + SMA_WARMUP
                if len(price_df) > load_rows:
                    price_df = price_df.iloc[-load_rows:]

            features_df = build_feature_dataframe(
                price_df["adj_close"],
                vix_closes=vix_closes,
                spy_closes=spy_closes,
            )

            async with async_session_factory() as db:
                rows = await _bulk_upsert_features(features_df, ticker, db)

            stats["tickers_processed"] += 1
            stats["total_rows"] += rows
            logger.info(
                "[%d/%d] %s — %d feature rows written",
                i,
                len(ticker_list),
                ticker,
                rows,
            )

        except Exception:
            logger.exception("[%d/%d] %s — FAILED", i, len(ticker_list), ticker)
            stats["errors"].append(ticker)

    elapsed = time.monotonic() - start
    logger.info(
        "Backfill complete: %d tickers, %d rows, %d skipped, %d errors in %.1fs",
        stats["tickers_processed"],
        stats["total_rows"],
        stats["skipped"],
        len(stats["errors"]),
        elapsed,
    )
    return stats


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill historical_features table from stock_prices"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific tickers to backfill (default: all)",
    )
    parser.add_argument(
        "--max-days",
        type=int,
        default=None,
        help="Limit to last N trading days per ticker",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing data",
    )
    args = parser.parse_args()

    asyncio.run(
        run_backfill(
            tickers=args.tickers,
            max_days=args.max_days,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
