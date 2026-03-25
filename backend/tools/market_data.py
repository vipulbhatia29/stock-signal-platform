"""Market data tool — fetch OHLCV prices from yfinance and store to TimescaleDB.

This module is the data pipeline entry point. Before we can compute any signals
(RSI, MACD, etc.), we need historical price data. yfinance is a free library
that pulls daily Open/High/Low/Close/Volume (OHLCV) data from Yahoo Finance.

The flow is:
  1. Call yfinance in a background thread (it's synchronous / blocking)
  2. Convert the returned DataFrame into StockPrice ORM rows
  3. Upsert them into TimescaleDB (skip rows that already exist)

Key concepts:
  - "OHLCV" = Open, High, Low, Close, Volume — the five data points per day
  - "Upsert" = INSERT ... ON CONFLICT DO NOTHING — idempotent writes
  - We run yfinance in a thread pool because FastAPI is async and we don't
    want a slow HTTP call to block the entire event loop
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.price import StockPrice
from backend.models.stock import Stock

logger = logging.getLogger(__name__)


async def fetch_prices(
    ticker: str,
    period: str = "10y",
    db: AsyncSession | None = None,
) -> pd.DataFrame:
    """Fetch historical OHLCV data for a stock ticker from Yahoo Finance.

    This is the main entry point for getting price data. It:
      1. Downloads data from Yahoo Finance via yfinance
      2. Optionally stores it in our database (if a db session is provided)
      3. Returns the data as a pandas DataFrame for further processing

    Args:
        ticker: Stock symbol, e.g. "AAPL", "MSFT", "GOOGL".
        period: How far back to fetch. Options: "1mo", "3mo", "6mo",
                "1y", "2y", "5y", "10y", "max". Default is "10y" because
                we need ~252 trading days minimum for signal calculations.
        db: Optional async database session. If provided, prices are
            stored (upserted) into the stock_prices table.

    Returns:
        A pandas DataFrame with columns: Open, High, Low, Close, Adj Close,
        Volume. Index is a DatetimeIndex of trading days.

    Raises:
        ValueError: If the ticker is invalid or yfinance returns no data.
    """
    # ── Step 1: Download from Yahoo Finance ──────────────────────────
    # yfinance is a synchronous (blocking) library — it makes HTTP calls
    # under the hood. We use asyncio.to_thread() to run it in a separate
    # thread so it doesn't block our async event loop.
    #
    # Think of it like this: our FastAPI server can handle many requests
    # at once because it's async. If we called yfinance directly, the
    # entire server would freeze while waiting for Yahoo's response.
    # asyncio.to_thread() moves that blocking call to a worker thread.
    df = await asyncio.to_thread(_download_ticker, ticker, period)

    if df.empty:
        raise ValueError(
            f"No price data returned for ticker '{ticker}'. "
            "Check that the ticker symbol is valid (e.g., 'AAPL', 'MSFT')."
        )

    logger.info("Fetched %d rows for %s (period=%s)", len(df), ticker, period)

    # ── Step 2: Store in database if session provided ────────────────
    if db is not None:
        await _store_prices(ticker, df, db)

    return df


def _download_ticker(ticker: str, period: str) -> pd.DataFrame:
    """Synchronous helper — download OHLCV data via yfinance.

    This runs inside asyncio.to_thread(), so it's okay that it blocks.
    We keep it as a separate function for two reasons:
      1. It's easier to mock in tests (we can patch this one function)
      2. asyncio.to_thread() needs a callable to run

    Args:
        ticker: Stock symbol like "AAPL".
        period: Lookback period like "10y".

    Returns:
        DataFrame with OHLCV columns, or an empty DataFrame if download fails.
    """
    try:
        # yf.download() returns a DataFrame with a DatetimeIndex
        # auto_adjust=False gives us both "Close" and "Adj Close" columns
        # — "Adj Close" accounts for stock splits and dividends
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=False,
            progress=False,  # suppress the progress bar in logs
        )
        # yfinance sometimes returns MultiIndex columns for single tickers.
        # Flatten them so we always get simple column names like "Open", "Close".
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        logger.exception("yfinance download failed for %s", ticker)
        return pd.DataFrame()


async def _store_prices(
    ticker: str,
    df: pd.DataFrame,
    db: AsyncSession,
) -> int:
    """Upsert price rows into the stock_prices table.

    "Upsert" means: INSERT the row, but if a row with the same (time, ticker)
    already exists, skip it (ON CONFLICT DO NOTHING). This makes the operation
    idempotent — you can run it multiple times and it won't create duplicates.

    We use PostgreSQL's INSERT ... ON CONFLICT because TimescaleDB hypertables
    don't support SQLAlchemy's merge() or standard upsert patterns well.

    Args:
        ticker: The stock ticker symbol.
        df: DataFrame from yfinance with OHLCV columns.
        db: Async database session.

    Returns:
        Number of rows inserted (excluding skipped duplicates).
    """
    if df.empty:
        return 0

    # ── Convert DataFrame rows into a list of dicts ──────────────────
    # Each dict represents one day of price data. We normalize the column
    # names to match our StockPrice model's column names.
    rows: list[dict] = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "time": idx.to_pydatetime().replace(tzinfo=timezone.utc),
                "ticker": ticker.upper(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "adj_close": float(row["Adj Close"]),
                "volume": int(row["Volume"]),
                "source": "yfinance",
            }
        )

    # ── Batch upsert using PostgreSQL's ON CONFLICT ──────────────────
    # pg_insert() is SQLAlchemy's PostgreSQL-specific INSERT that supports
    # ON CONFLICT. We use on_conflict_do_update() so existing rows are
    # updated with the latest price data (handles post-settlement corrections).
    #
    # We batch in chunks of 500 to avoid sending a massive SQL statement
    # that could time out or use too much memory.
    chunk_size = 500
    upserted = 0

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        stmt = pg_insert(StockPrice).values(chunk)
        stmt = stmt.on_conflict_do_update(
            # The conflict target is the composite primary key (time, ticker).
            index_elements=["time", "ticker"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "adj_close": stmt.excluded.adj_close,
                "volume": stmt.excluded.volume,
            },
        )
        result = await db.execute(stmt)
        upserted += result.rowcount

    await db.commit()
    logger.info(
        "Upserted %d price rows for %s (%d total fetched)",
        upserted,
        ticker,
        len(rows),
    )

    return upserted


async def ensure_stock_exists(
    ticker: str,
    db: AsyncSession,
) -> Stock:
    """Make sure a Stock record exists in the database for this ticker.

    When a user requests data for a new ticker, we first need to create
    a record in the 'stocks' table. This function checks if one exists
    and creates it if not, using yfinance to look up the company name
    and sector.

    Args:
        ticker: Stock symbol like "AAPL".
        db: Async database session.

    Returns:
        The Stock ORM object (either existing or newly created).

    Raises:
        ValueError: If yfinance can't find info for this ticker.
    """
    # ── Check if stock already exists ────────────────────────────────
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()

    if stock is not None:
        return stock

    # ── Look up stock info from yfinance ─────────────────────────────
    # yf.Ticker().info is a dict with company details. We run it in a
    # thread because it makes an HTTP call.
    info = await asyncio.to_thread(_get_ticker_info, ticker)

    if not info or info.get("regularMarketPrice") is None:
        raise ValueError(
            f"Could not find stock info for '{ticker}'. Make sure the ticker symbol is correct."
        )

    # ── Create the Stock record ──────────────────────────────────────
    stock = Stock(
        ticker=ticker.upper(),
        name=info.get("shortName", info.get("longName", ticker.upper())),
        exchange=info.get("exchange"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        is_active=True,
    )
    db.add(stock)
    await db.commit()
    await db.refresh(stock)

    logger.info("Created new Stock record: %s (%s)", stock.ticker, stock.name)
    return stock


def _get_ticker_info(ticker: str) -> dict:
    """Synchronous helper — fetch stock metadata from yfinance.

    Returns a dict with keys like 'shortName', 'sector', 'industry', etc.
    This runs inside asyncio.to_thread().
    """
    try:
        return yf.Ticker(ticker).info
    except Exception:
        logger.exception("Failed to fetch info for %s", ticker)
        return {}


async def fetch_prices_delta(
    ticker: str,
    db: AsyncSession,
) -> pd.DataFrame:
    """Fetch only new price data since the last stored row for a ticker.

    Queries MAX(time) from stock_prices for this ticker, then fetches
    data from that date forward. If no data exists, fetches full 10Y.
    Uses the existing upsert logic so overlapping rows are skipped.

    Args:
        ticker: Stock symbol like "AAPL".
        db: Async database session.

    Returns:
        DataFrame of newly fetched data (may include overlap rows).
    """
    result = await db.execute(
        select(func.max(StockPrice.time)).where(StockPrice.ticker == ticker.upper())
    )
    max_time = result.scalar_one_or_none()

    if max_time is None:
        logger.info("No existing data for %s, fetching full 10Y", ticker)
        return await fetch_prices(ticker, period="10y", db=db)

    # yfinance start parameter expects a string "YYYY-MM-DD"
    start_date = max_time.strftime("%Y-%m-%d")
    logger.info("Delta fetch for %s from %s", ticker, start_date)

    df = await asyncio.to_thread(_download_ticker_range, ticker, start_date)

    if df.empty:
        logger.info("No new data for %s since %s", ticker, start_date)
        return df

    await _store_prices(ticker, df, db)
    return df


async def load_prices_df(ticker: str, db: AsyncSession) -> pd.DataFrame:
    """Load all stored prices for a ticker from the database as a DataFrame.

    Returns a DataFrame with the same column layout that compute_signals
    expects (Open, High, Low, Close, Adj Close, Volume) indexed by date.

    Args:
        ticker: Stock symbol.
        db: Async database session.

    Returns:
        DataFrame of historical prices, or empty DataFrame if none found.
    """
    result = await db.execute(
        select(StockPrice).where(StockPrice.ticker == ticker.upper()).order_by(StockPrice.time)
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()

    data = {
        "Open": [float(r.open) for r in rows],
        "High": [float(r.high) for r in rows],
        "Low": [float(r.low) for r in rows],
        "Close": [float(r.close) for r in rows],
        "Adj Close": [float(r.adj_close) for r in rows],
        "Volume": [int(r.volume) for r in rows],
    }
    index = pd.DatetimeIndex([r.time for r in rows])
    return pd.DataFrame(data, index=index)


async def update_last_fetched_at(ticker: str, db: AsyncSession) -> None:
    """Update the Stock.last_fetched_at timestamp after a successful fetch.

    Args:
        ticker: Stock symbol.
        db: Async database session.
    """
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if stock is not None:
        stock.last_fetched_at = datetime.now(timezone.utc)
        await db.commit()


def _download_ticker_range(ticker: str, start: str) -> pd.DataFrame:
    """Synchronous helper — download OHLCV data from a start date to today.

    Args:
        ticker: Stock symbol.
        start: Start date as "YYYY-MM-DD".

    Returns:
        DataFrame with OHLCV columns.
    """
    try:
        df = yf.download(
            ticker,
            start=start,
            auto_adjust=False,
            progress=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        logger.exception("yfinance range download failed for %s", ticker)
        return pd.DataFrame()


async def get_latest_price(ticker: str, db: AsyncSession) -> float | None:
    """Get the most recent closing price for a ticker from our database.

    This queries the stock_prices table and returns the latest adj_close.
    We use adj_close (adjusted close) because it accounts for stock splits
    and dividends, giving us the "true" price for calculations.

    Args:
        ticker: Stock symbol.
        db: Async database session.

    Returns:
        The latest adjusted close price, or None if no data exists.
    """
    result = await db.execute(
        select(StockPrice.adj_close)
        .where(StockPrice.ticker == ticker.upper())
        .order_by(StockPrice.time.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else None
