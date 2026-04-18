"""Stock data service — price CRUD, stock lifecycle, and fundamentals persistence.

Extracted from tools/market_data.py and tools/fundamentals.py so that routers,
tasks, and tool classes all share a single source of truth for DB-touching
business logic.  Every function preserves its original signature so existing
call-sites continue to work after re-export.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.observability.instrumentation.yfinance_session import get_yfinance_session
from backend.services.rate_limiter import yfinance_limiter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals result dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FundamentalResult:
    """Container for all fundamental metrics for a single ticker.

    Fields that cannot be computed (missing yfinance data) are set to None.
    This lets callers distinguish "not available" from "zero".
    """

    ticker: str

    # Valuation
    pe_ratio: float | None
    peg_ratio: float | None
    fcf_yield: float | None  # 0.05 = 5%
    debt_to_equity: float | None  # e.g. 0.5 = 50% debt relative to equity

    # Piotroski
    piotroski_score: int | None  # 0–9

    # Growth & margins (materialized to Stock model during ingestion)
    revenue_growth: float | None = None
    gross_margins: float | None = None
    operating_margins: float | None = None
    profit_margins: float | None = None
    return_on_equity: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None

    piotroski_breakdown: dict = field(default_factory=dict)  # 9 binary criteria


# ─────────────────────────────────────────────────────────────────────────────
# Piotroski F-Score computation
# ─────────────────────────────────────────────────────────────────────────────


def compute_piotroski(info: dict) -> tuple[int | None, dict]:
    """Compute the Piotroski F-Score from a yfinance info dict.

    Each of the 9 criteria returns 1 if met, 0 if not, or is skipped if data
    is missing. If no criteria can be evaluated, returns (None, {}).

    Args:
        info: yfinance Ticker.info dictionary (or equivalent flat dict).

    Returns:
        Tuple of (total_score, breakdown_dict).
        breakdown_dict maps criterion name to 0 or 1.
        If data is insufficient, returns (None, {}).
    """
    if not info:
        return None, {}

    breakdown: dict[str, int] = {}

    # ── Helper: safe float fetch ─────────────────────────────────────
    def _get(key: str) -> float | None:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    roa = _get("returnOnAssets")
    roa_prior = _get("returnOnAssetsPrior")
    cfo = _get("operatingCashflow")
    total_assets = _get("totalAssets")
    long_term_debt = _get("longTermDebt")
    long_term_debt_prior = _get("longTermDebtPrior")
    current_ratio = _get("currentRatio")
    current_ratio_prior = _get("currentRatioPrior")
    shares = _get("sharesOutstanding")
    shares_prior = _get("sharesPrior")
    gross_margin = _get("grossMargins")
    gross_margin_prior = _get("grossMarginsPrior")
    asset_turnover = _get("assetTurnover")
    asset_turnover_prior = _get("assetTurnoverPrior")

    # ── F1: Positive ROA ─────────────────────────────────────────────
    if roa is not None:
        breakdown["positive_roa"] = 1 if roa > 0 else 0

    # ── F2: Positive operating cash flow ─────────────────────────────
    if cfo is not None:
        breakdown["positive_cfo"] = 1 if cfo > 0 else 0

    # ── F3: Improving ROA ────────────────────────────────────────────
    if roa is not None and roa_prior is not None:
        breakdown["improving_roa"] = 1 if roa > roa_prior else 0

    # ── F4: Accruals — CFO > Net Income (ROA × Total Assets) ─────────
    if cfo is not None and roa is not None and total_assets is not None:
        net_income_est = roa * total_assets
        breakdown["accruals"] = 1 if cfo > net_income_est else 0

    # ── F5: Decreasing long-term debt ────────────────────────────────
    if long_term_debt is not None and long_term_debt_prior is not None:
        breakdown["decreasing_leverage"] = 1 if long_term_debt < long_term_debt_prior else 0

    # ── F6: Improving current ratio ──────────────────────────────────
    if current_ratio is not None and current_ratio_prior is not None:
        breakdown["improving_liquidity"] = 1 if current_ratio > current_ratio_prior else 0

    # ── F7: No share dilution ────────────────────────────────────────
    if shares is not None and shares_prior is not None:
        breakdown["no_dilution"] = 1 if shares <= shares_prior else 0

    # ── F8: Improving gross margin ───────────────────────────────────
    if gross_margin is not None and gross_margin_prior is not None:
        breakdown["improving_gross_margin"] = 1 if gross_margin > gross_margin_prior else 0

    # ── F9: Improving asset turnover ─────────────────────────────────
    if asset_turnover is not None and asset_turnover_prior is not None:
        breakdown["improving_asset_turnover"] = 1 if asset_turnover > asset_turnover_prior else 0

    if not breakdown:
        return None, {}

    total = sum(breakdown.values())
    return total, breakdown


# ─────────────────────────────────────────────────────────────────────────────
# Stock lifecycle — ensure_stock_exists
# ─────────────────────────────────────────────────────────────────────────────


def _get_ticker_info(ticker: str) -> dict:
    """Synchronous helper — fetch stock metadata from yfinance.

    Returns a dict with keys like 'shortName', 'sector', 'industry', etc.
    This runs inside asyncio.to_thread().
    """
    try:
        return yf.Ticker(ticker, session=get_yfinance_session()).info
    except Exception:
        logger.exception("Failed to fetch info for %s", ticker)
        return {}


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
    await yfinance_limiter.acquire()
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


# ─────────────────────────────────────────────────────────────────────────────
# Price fetching and storage
# ─────────────────────────────────────────────────────────────────────────────


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
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=False,
            progress=False,
            session=get_yfinance_session(),
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        logger.exception("yfinance download failed for %s", ticker)
        return pd.DataFrame()


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
            session=get_yfinance_session(),
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        logger.exception("yfinance range download failed for %s", ticker)
        return pd.DataFrame()


async def _store_prices(
    ticker: str,
    df: pd.DataFrame,
    db: AsyncSession,
) -> int:
    """Upsert price rows into the stock_prices table.

    "Upsert" means: INSERT the row, but if a row with the same (time, ticker)
    already exists, update it. This makes the operation idempotent.

    Args:
        ticker: The stock ticker symbol.
        df: DataFrame from yfinance with OHLCV columns.
        db: Async database session.

    Returns:
        Number of rows inserted (excluding skipped duplicates).
    """
    if df.empty:
        return 0

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

    chunk_size = 500
    upserted = 0

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        stmt = pg_insert(StockPrice).values(chunk)
        stmt = stmt.on_conflict_do_update(
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
                "1y", "2y", "5y", "10y", "max". Default is "10y".
        db: Optional async database session. If provided, prices are
            stored (upserted) into the stock_prices table.

    Returns:
        A pandas DataFrame with columns: Open, High, Low, Close, Adj Close,
        Volume. Index is a DatetimeIndex of trading days.

    Raises:
        ValueError: If the ticker is invalid or yfinance returns no data.
    """
    await yfinance_limiter.acquire()
    df = await asyncio.to_thread(_download_ticker, ticker, period)

    if df.empty:
        raise ValueError(
            f"No price data returned for ticker '{ticker}'. "
            "Check that the ticker symbol is valid (e.g., 'AAPL', 'MSFT')."
        )

    logger.info("Fetched %d rows for %s (period=%s)", len(df), ticker, period)

    if db is not None:
        await _store_prices(ticker, df, db)

    return df


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

    start_date = max_time.strftime("%Y-%m-%d")
    logger.info("Delta fetch for %s from %s", ticker, start_date)

    await yfinance_limiter.acquire()
    df = await asyncio.to_thread(_download_ticker_range, ticker, start_date)

    if df.empty:
        logger.info("No new data for %s since %s", ticker, start_date)
        return df

    await _store_prices(ticker, df, db)
    return df


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


# ─────────────────────────────────────────────────────────────────────────────
# Fundamentals — fetch (sync, yfinance)
# ─────────────────────────────────────────────────────────────────────────────


def _null_result(ticker: str) -> FundamentalResult:
    """Return an all-None FundamentalResult for a given ticker."""
    return FundamentalResult(
        ticker=ticker.upper(),
        pe_ratio=None,
        peg_ratio=None,
        fcf_yield=None,
        debt_to_equity=None,
        piotroski_score=None,
        piotroski_breakdown={},
    )


def fetch_fundamentals(ticker: str) -> FundamentalResult:
    """Fetch and compute fundamental metrics for a ticker via yfinance.

    Calls yfinance synchronously (this is a CPU/IO-bound operation that
    should be run in a thread pool when called from async FastAPI context).

    Args:
        ticker: Stock symbol (e.g. "AAPL"). Case-insensitive.

    Returns:
        FundamentalResult with all available metrics. Fields are None
        when yfinance does not provide the data.
    """
    ticker = ticker.upper().strip()

    try:
        t = yf.Ticker(ticker, session=get_yfinance_session())
        info = t.info or {}
    except Exception:
        logger.warning("yfinance failed for %s fundamentals", ticker)
        return _null_result(ticker)

    # ── Valuation ratios ─────────────────────────────────────────────
    def _get(key: str) -> float | None:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    pe_ratio = _get("trailingPE")
    peg_ratio = _get("pegRatio")
    debt_to_equity = _get("debtToEquity")

    # FCF yield = Free Cash Flow / Market Cap
    fcf = _get("freeCashflow")
    market_cap = _get("marketCap")
    if fcf is not None and market_cap and market_cap > 0:
        fcf_yield = round(fcf / market_cap, 4)
    else:
        fcf_yield = None

    # ── Growth & margins ─────────────────────────────────────────────
    revenue_growth = _get("revenueGrowth")
    gross_margins = _get("grossMargins")
    operating_margins = _get("operatingMargins")
    profit_margins = _get("profitMargins")
    return_on_equity = _get("returnOnEquity")
    enterprise_value = _get("enterpriseValue")

    # ── Piotroski F-Score ────────────────────────────────────────────
    piotroski_score, piotroski_breakdown = compute_piotroski(info)

    logger.info(
        "Fundamentals fetched for %s: PE=%.1f PEG=%.2f FCF_yield=%.3f Piotroski=%s",
        ticker,
        pe_ratio or 0,
        peg_ratio or 0,
        fcf_yield or 0,
        piotroski_score,
    )

    return FundamentalResult(
        ticker=ticker,
        pe_ratio=pe_ratio,
        peg_ratio=peg_ratio,
        fcf_yield=fcf_yield,
        debt_to_equity=debt_to_equity,
        revenue_growth=revenue_growth,
        gross_margins=gross_margins,
        operating_margins=operating_margins,
        profit_margins=profit_margins,
        return_on_equity=return_on_equity,
        market_cap=market_cap,
        enterprise_value=enterprise_value,
        piotroski_score=piotroski_score,
        piotroski_breakdown=piotroski_breakdown,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Analyst data — fetch (sync, yfinance)
# ─────────────────────────────────────────────────────────────────────────────


def fetch_analyst_data(ticker: str) -> dict:
    """Fetch analyst target and recommendation data from yfinance.

    Args:
        ticker: Stock symbol.

    Returns:
        Dict with analyst_target_mean/high/low, analyst_buy/hold/sell,
        business_summary, employees, website. Missing keys are omitted.
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker, session=get_yfinance_session())
        info = t.info or {}
    except Exception:
        logger.warning("yfinance failed for %s analyst data", ticker)
        return {}

    def _get_float(key: str) -> float | None:
        val = info.get(key)
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _get_int(key: str) -> int | None:
        val = info.get(key)
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    result: dict = {}

    # Analyst targets
    for key, field_name in [
        ("targetMeanPrice", "analyst_target_mean"),
        ("targetHighPrice", "analyst_target_high"),
        ("targetLowPrice", "analyst_target_low"),
    ]:
        val = _get_float(key)
        if val is not None:
            result[field_name] = val

    # Recommendation breakdown
    recs = info.get("recommendationKey")  # noqa: F841 — we use breakdown below
    for key, field_name in [
        ("numberOfAnalystOpinions", "analyst_buy"),  # approximate; see below
    ]:
        pass  # yfinance doesn't split buy/hold/sell reliably from .info

    # Use .recommendations_summary if available for buy/hold/sell counts
    try:
        rec_summary = t.recommendations
        if rec_summary is not None and not rec_summary.empty:
            latest = rec_summary.iloc[-1]
            result["analyst_buy"] = int(latest.get("strongBuy", 0)) + int(latest.get("buy", 0))
            result["analyst_hold"] = int(latest.get("hold", 0))
            result["analyst_sell"] = int(latest.get("sell", 0)) + int(latest.get("strongSell", 0))
    except Exception:
        pass

    # Profile data
    summary = info.get("longBusinessSummary")
    if summary:
        result["business_summary"] = summary
    employees = _get_int("fullTimeEmployees")
    if employees is not None:
        result["employees"] = employees
    website = info.get("website")
    if website:
        result["website"] = str(website)

    # Market risk & income (for portfolio health computation)
    for yf_key, field_name in [
        ("beta", "beta"),
        ("dividendYield", "dividend_yield"),
        ("forwardPE", "forward_pe"),
    ]:
        val = _get_float(yf_key)
        if val is not None:
            result[field_name] = val

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Earnings history — fetch (sync, yfinance)
# ─────────────────────────────────────────────────────────────────────────────


def fetch_earnings_history(ticker: str) -> list[dict]:
    """Fetch quarterly earnings history from yfinance.

    Args:
        ticker: Stock symbol.

    Returns:
        List of dicts with keys: quarter, eps_estimate, eps_actual, surprise_pct.
        Empty list on failure.
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker, session=get_yfinance_session())
        hist = t.earnings_history
        if hist is None or hist.empty:
            return []
    except Exception:
        logger.warning("yfinance failed for %s earnings history", ticker)
        return []

    results = []
    for idx, row in hist.iterrows():
        if hasattr(idx, "quarter"):
            quarter = f"{idx.year}Q{idx.quarter}"
        else:
            quarter = str(idx) if idx else ""

        eps_est = row.get("epsEstimate")
        eps_act = row.get("epsActual")
        surprise = row.get("surprisePercent")

        def _safe_float(v: object) -> float | None:
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        results.append(
            {
                "quarter": quarter,
                "eps_estimate": _safe_float(eps_est),
                "eps_actual": _safe_float(eps_act),
                "surprise_pct": _safe_float(surprise),
            }
        )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Persist — enriched fundamentals, analyst data, earnings snapshots
# ─────────────────────────────────────────────────────────────────────────────


async def persist_enriched_fundamentals(
    stock: Stock,
    fundamentals: FundamentalResult,
    analyst_data: dict,
    db: AsyncSession,
) -> None:
    """Persist enriched fundamentals and analyst data to the Stock model.

    Args:
        stock: Stock ORM object to update.
        fundamentals: FundamentalResult from fetch_fundamentals().
        analyst_data: Dict from fetch_analyst_data().
        db: Async database session (caller manages commit).
    """
    # Growth & margins from FundamentalResult
    stock.revenue_growth = fundamentals.revenue_growth
    stock.gross_margins = fundamentals.gross_margins
    stock.operating_margins = fundamentals.operating_margins
    stock.profit_margins = fundamentals.profit_margins
    stock.return_on_equity = fundamentals.return_on_equity
    stock.market_cap = fundamentals.market_cap

    # Analyst data
    for field_name in (
        "analyst_target_mean",
        "analyst_target_high",
        "analyst_target_low",
        "analyst_buy",
        "analyst_hold",
        "analyst_sell",
        "business_summary",
        "employees",
        "website",
    ):
        val = analyst_data.get(field_name)
        if val is not None:
            setattr(stock, field_name, val)

    db.add(stock)
    logger.info("Persisted enriched fundamentals for %s", stock.ticker)


async def persist_earnings_snapshots(
    ticker: str,
    earnings: list[dict],
    db: AsyncSession,
) -> int:
    """Upsert earnings snapshots into the database.

    Args:
        ticker: Stock ticker.
        earnings: List of dicts from fetch_earnings_history().
        db: Async session (caller manages commit).

    Returns:
        Number of rows upserted.
    """
    if not earnings:
        return 0

    from sqlalchemy.dialects.postgresql import insert

    from backend.models.earnings import EarningsSnapshot

    rows = []
    for e in earnings:
        if not e.get("quarter"):
            continue
        rows.append(
            {
                "ticker": ticker.upper(),
                "quarter": e["quarter"],
                "eps_estimate": e.get("eps_estimate"),
                "eps_actual": e.get("eps_actual"),
                "surprise_pct": e.get("surprise_pct"),
            }
        )

    if not rows:
        return 0

    stmt = insert(EarningsSnapshot).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="earnings_snapshots_pkey",
        set_={
            "eps_estimate": stmt.excluded.eps_estimate,
            "eps_actual": stmt.excluded.eps_actual,
            "surprise_pct": stmt.excluded.surprise_pct,
        },
    )
    await db.execute(stmt)
    logger.info("Upserted %d earnings snapshots for %s", len(rows), ticker)
    return len(rows)
