"""Signal computation and query service.

Extracts signal computation logic (previously in tools/signals.py) and
signal query logic (previously inline in routers/stocks.py) into a
dedicated service layer.

Public API:
  - SignalResult: dataclass holding all computed signals for a ticker
  - compute_signals(): compute all technical indicators from OHLCV data
  - store_signal_snapshot(): persist a SignalResult to the database
  - get_latest_signals(): fetch the most recent signal snapshot for a ticker
  - get_signal_history(): fetch chronological signal snapshots for charting
  - get_bulk_signals(): fetch latest signals per ticker with filters (screener)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import Float, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.index import StockIndexMembership
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants — these are standard values used across the finance industry.
# You'll see these same numbers in TradingView, Bloomberg, etc.
# ─────────────────────────────────────────────────────────────────────────────
RSI_PERIOD = 14  # 14-day RSI is the industry standard
RSI_OVERSOLD = 30  # Below 30 = oversold
RSI_OVERBOUGHT = 70  # Above 70 = overbought

MACD_FAST = 12  # 12-day EMA (fast line)
MACD_SLOW = 26  # 26-day EMA (slow line)
MACD_SIGNAL = 9  # 9-day EMA of MACD (signal line)

SMA_SHORT = 50  # 50-day Simple Moving Average
SMA_LONG = 200  # 200-day Simple Moving Average

BB_PERIOD = 20  # 20-day Bollinger Band
BB_STD_DEV = 2  # 2 standard deviations for band width

TRADING_DAYS_PER_YEAR = 252  # Approx. trading days in a year (excludes weekends/holidays)

DEFAULT_RISK_FREE_RATE = 0.045  # 4.5% — used when we can't fetch from FRED API


# ─────────────────────────────────────────────────────────────────────────────
# Signal Labels — the human-readable labels we assign to each indicator.
# These are stored in the database alongside the numeric values.
# ─────────────────────────────────────────────────────────────────────────────
class RSISignal:
    OVERSOLD = "OVERSOLD"  # RSI < 30 → potential buying opportunity
    NEUTRAL = "NEUTRAL"  # RSI 30-70 → no clear signal
    OVERBOUGHT = "OVERBOUGHT"  # RSI > 70 → may be overvalued


class MACDSignal:
    BULLISH = "BULLISH"  # Histogram > 0 → upward momentum
    BEARISH = "BEARISH"  # Histogram <= 0 → downward momentum


class SMASignal:
    GOLDEN_CROSS = "GOLDEN_CROSS"  # 50-day just crossed above 200-day → strong BUY
    DEATH_CROSS = "DEATH_CROSS"  # 50-day just crossed below 200-day → strong SELL
    ABOVE_200 = "ABOVE_200"  # Price above 200-day SMA → healthy uptrend
    BELOW_200 = "BELOW_200"  # Price below 200-day SMA → potential downtrend


class BBSignal:
    UPPER = "UPPER"  # Price above upper Bollinger Band → may be overbought
    MIDDLE = "MIDDLE"  # Price between bands → normal range
    LOWER = "LOWER"  # Price below lower Bollinger Band → may be oversold


# ─────────────────────────────────────────────────────────────────────────────
# Data class to hold all computed signals for a single stock.
# Using a dataclass makes it easy to pass results around and access fields.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SignalResult:
    """Container for all computed signals for a single ticker.

    This is returned by compute_signals() and contains every indicator
    value plus the labels and composite score. Think of it as a "report
    card" for a stock's technical health.
    """

    ticker: str

    # RSI — momentum indicator (0-100)
    rsi_value: float | None
    rsi_signal: str | None  # OVERSOLD, NEUTRAL, or OVERBOUGHT

    # MACD — trend direction
    macd_value: float | None  # MACD line value
    macd_histogram: float | None  # Difference between MACD and signal line
    macd_signal_label: str | None  # BULLISH or BEARISH

    # SMA — long-term trend
    sma_50: float | None  # 50-day simple moving average
    sma_200: float | None  # 200-day simple moving average
    sma_signal: str | None  # GOLDEN_CROSS, DEATH_CROSS, etc.

    # Bollinger Bands — volatility measure
    bb_upper: float | None  # Upper band (mean + 2*stdev)
    bb_lower: float | None  # Lower band (mean - 2*stdev)
    bb_position: str | None  # UPPER, MIDDLE, or LOWER

    # Risk/Return metrics
    annual_return: float | None  # Annualized return (e.g., 0.15 = 15%)
    volatility: float | None  # Annualized volatility (e.g., 0.20 = 20%)
    sharpe_ratio: float | None  # Risk-adjusted return

    # Composite score (0-10 scale)
    composite_score: float | None
    composite_weights: dict | None  # Records which weights were used

    # Price change (daily)
    change_pct: float | None = None  # daily price change percentage
    current_price: float | None = None  # latest close price


def compute_price_change(
    df: pd.DataFrame | None,
) -> tuple[float | None, float | None]:
    """Compute daily price change percentage and current price.

    Returns (change_pct, current_price).
    """
    import math

    if df is None or len(df) < 2:
        return None, None
    for col in ("adj_close", "Adj Close", "close", "Close"):
        if col in df.columns:
            closes = df[col]
            break
    else:
        return None, None
    current = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    if not math.isfinite(current) or not math.isfinite(previous):
        return None, None
    if previous == 0:
        return None, current
    change = ((current - previous) / previous) * 100
    return round(change, 2), round(current, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point — compute all signals for a ticker
# ─────────────────────────────────────────────────────────────────────────────
def compute_signals(
    ticker: str,
    df: pd.DataFrame,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
    piotroski_score: int | None = None,
) -> SignalResult:
    """Compute all technical signals for a stock from its price history.

    This is the main function you call. It takes a DataFrame of OHLCV data
    (from yfinance or our database) and returns a SignalResult with every
    indicator computed.

    Args:
        ticker: Stock symbol like "AAPL".
        df: DataFrame with at least a "Close" column (or "Adj Close") and
            a DatetimeIndex. Should have 200+ rows for SMA calculations.
        risk_free_rate: Annual risk-free rate for Sharpe ratio calculation.
            Default 4.5% — this approximates the current US Treasury yield.
        piotroski_score: Optional Piotroski F-Score (0-9) for fundamental
            blending. When provided, composite score uses 50% technical +
            50% fundamental. When None, falls back to 100% technical.

    Returns:
        A SignalResult dataclass with all indicator values and labels.
    """
    # ── Determine which price column to use ──────────────────────────
    close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    closes = df[close_col].dropna()

    # ── Guard: we need enough data to compute signals ────────────────
    if len(closes) < RSI_PERIOD + 1:
        logger.warning("Not enough data for %s: only %d rows", ticker, len(closes))
        return SignalResult(
            ticker=ticker,
            rsi_value=None,
            rsi_signal=None,
            macd_value=None,
            macd_histogram=None,
            macd_signal_label=None,
            sma_50=None,
            sma_200=None,
            sma_signal=None,
            bb_upper=None,
            bb_lower=None,
            bb_position=None,
            annual_return=None,
            volatility=None,
            sharpe_ratio=None,
            composite_score=None,
            composite_weights=None,
        )

    # ── Compute each indicator ───────────────────────────────────────
    rsi_val, rsi_sig = compute_rsi(closes)
    macd_val, macd_hist, macd_sig = compute_macd(closes)
    sma50, sma200, sma_sig = compute_sma(closes)
    bb_up, bb_low, bb_pos = compute_bollinger(closes)
    ann_ret, vol, sharpe = compute_risk_return(closes, risk_free_rate)

    # ── Compute composite score ──────────────────────────────────────
    score, weights = compute_composite_score(
        rsi_val,
        rsi_sig,
        macd_hist,
        macd_sig,
        sma_sig,
        sharpe,
        piotroski_score=piotroski_score,
    )

    change_pct, current_price = compute_price_change(df)

    return SignalResult(
        ticker=ticker,
        rsi_value=rsi_val,
        rsi_signal=rsi_sig,
        macd_value=macd_val,
        macd_histogram=macd_hist,
        macd_signal_label=macd_sig,
        sma_50=sma50,
        sma_200=sma200,
        sma_signal=sma_sig,
        bb_upper=bb_up,
        bb_lower=bb_low,
        bb_position=bb_pos,
        annual_return=ann_ret,
        volatility=vol,
        sharpe_ratio=sharpe,
        composite_score=score,
        composite_weights=weights,
        change_pct=change_pct,
        current_price=current_price,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Individual indicator calculations
# ─────────────────────────────────────────────────────────────────────────────


def compute_rsi(closes: pd.Series, period: int = RSI_PERIOD) -> tuple[float | None, str | None]:
    """Compute the RSI (Relative Strength Index).

    RSI measures how fast and how much a stock's price is changing.
    It oscillates between 0 and 100.

    Args:
        closes: Series of closing prices.
        period: Lookback period (default 14 days).

    Returns:
        Tuple of (rsi_value, signal_label).
    """
    if len(closes) < period + 1:
        return None, None

    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = losses.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    rsi_value = round(float(rsi.iloc[-1]), 2)

    if rsi_value < RSI_OVERSOLD:
        signal = RSISignal.OVERSOLD
    elif rsi_value > RSI_OVERBOUGHT:
        signal = RSISignal.OVERBOUGHT
    else:
        signal = RSISignal.NEUTRAL

    return rsi_value, signal


def compute_macd(
    closes: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal_period: int = MACD_SIGNAL,
) -> tuple[float | None, float | None, str | None]:
    """Compute MACD (Moving Average Convergence Divergence).

    Args:
        closes: Series of closing prices.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal_period: Signal line EMA period (default 9).

    Returns:
        Tuple of (macd_value, histogram_value, signal_label).
    """
    if len(closes) < slow + signal_period:
        return None, None, None

    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    macd_val = round(float(macd_line.iloc[-1]), 4)
    hist_val = round(float(histogram.iloc[-1]), 4)

    signal = MACDSignal.BULLISH if hist_val > 0 else MACDSignal.BEARISH

    return macd_val, hist_val, signal


def compute_sma(
    closes: pd.Series,
    short: int = SMA_SHORT,
    long: int = SMA_LONG,
) -> tuple[float | None, float | None, str | None]:
    """Compute Simple Moving Averages and detect crossover signals.

    Args:
        closes: Series of closing prices.
        short: Short-term SMA period (default 50).
        long: Long-term SMA period (default 200).

    Returns:
        Tuple of (sma_50_value, sma_200_value, signal_label).
    """
    sma_short = closes.rolling(window=short).mean() if len(closes) >= short else None
    sma_long = closes.rolling(window=long).mean() if len(closes) >= long else None

    sma50_val = (
        round(float(sma_short.iloc[-1]), 4)
        if sma_short is not None and not pd.isna(sma_short.iloc[-1])
        else None
    )
    sma200_val = (
        round(float(sma_long.iloc[-1]), 4)
        if sma_long is not None and not pd.isna(sma_long.iloc[-1])
        else None
    )

    if sma_short is None or sma_long is None or sma50_val is None or sma200_val is None:
        return sma50_val, sma200_val, None

    if len(sma_short) >= 2 and len(sma_long) >= 2:
        today_short = sma_short.iloc[-1]
        today_long = sma_long.iloc[-1]
        yesterday_short = sma_short.iloc[-2]
        yesterday_long = sma_long.iloc[-2]

        if yesterday_short <= yesterday_long and today_short > today_long:
            return sma50_val, sma200_val, SMASignal.GOLDEN_CROSS

        if yesterday_short >= yesterday_long and today_short < today_long:
            return sma50_val, sma200_val, SMASignal.DEATH_CROSS

    current_price = float(closes.iloc[-1])
    if current_price > sma200_val:
        signal = SMASignal.ABOVE_200
    else:
        signal = SMASignal.BELOW_200

    return sma50_val, sma200_val, signal


def compute_bollinger(
    closes: pd.Series,
    period: int = BB_PERIOD,
    num_std: float = BB_STD_DEV,
) -> tuple[float | None, float | None, str | None]:
    """Compute Bollinger Bands — a volatility-based envelope around price.

    Args:
        closes: Series of closing prices.
        period: Lookback period for the moving average (default 20).
        num_std: Number of standard deviations for band width (default 2).

    Returns:
        Tuple of (upper_band, lower_band, position_label).
    """
    if len(closes) < period:
        return None, None, None

    sma = closes.rolling(window=period).mean()
    std = closes.rolling(window=period).std()

    upper = sma + (num_std * std)
    lower = sma - (num_std * std)

    upper_val = round(float(upper.iloc[-1]), 4)
    lower_val = round(float(lower.iloc[-1]), 4)
    current_price = float(closes.iloc[-1])

    if current_price > upper_val:
        position = BBSignal.UPPER
    elif current_price < lower_val:
        position = BBSignal.LOWER
    else:
        position = BBSignal.MIDDLE

    return upper_val, lower_val, position


def compute_risk_return(
    closes: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> tuple[float | None, float | None, float | None]:
    """Compute annualized return, volatility, and Sharpe ratio.

    Args:
        closes: Series of closing prices.
        risk_free_rate: Annual risk-free rate (default 4.5%).

    Returns:
        Tuple of (annualized_return, volatility, sharpe_ratio).
    """
    if len(closes) < 2:
        return None, None, None

    daily_returns = closes.pct_change().dropna()

    if len(daily_returns) < 1:
        return None, None, None

    trading_days = len(daily_returns)

    total_return = float(closes.iloc[-1]) / float(closes.iloc[0])
    annualized = total_return ** (TRADING_DAYS_PER_YEAR / trading_days) - 1
    annualized = round(annualized, 4)

    daily_vol = float(daily_returns.std())
    vol = round(daily_vol * np.sqrt(TRADING_DAYS_PER_YEAR), 4)

    if vol == 0:
        sharpe = None
    else:
        sharpe = round((annualized - risk_free_rate) / vol, 4)

    return annualized, vol, sharpe


# ─────────────────────────────────────────────────────────────────────────────
# Composite score — combines all indicators into a single 0-10 number
# ─────────────────────────────────────────────────────────────────────────────


def compute_composite_score(
    rsi_value: float | None,
    rsi_signal: str | None,
    macd_histogram: float | None,
    macd_signal: str | None,
    sma_signal: str | None,
    sharpe: float | None,
    piotroski_score: int | None = None,
) -> tuple[float | None, dict | None]:
    """Compute the composite score (0-10) from technical and fundamental signals.

    Blending strategy (FSD FR-3.2):
      - When piotroski_score is provided: 50% technical + 50% fundamental
      - When piotroski_score is None: 100% technical (fallback for ETFs,
        new listings, or tickers with no earnings data)

    Args:
        rsi_value: RSI numeric value (0-100).
        rsi_signal: RSI label (OVERSOLD/NEUTRAL/OVERBOUGHT).
        macd_histogram: MACD histogram value.
        macd_signal: MACD label (BULLISH/BEARISH).
        sma_signal: SMA label (GOLDEN_CROSS/DEATH_CROSS/ABOVE_200/BELOW_200).
        sharpe: Sharpe ratio value.
        piotroski_score: Piotroski F-Score (0-9). None → 100% technical mode.

    Returns:
        Tuple of (composite_score, weights_dict).
    """
    if all(v is None for v in [rsi_value, macd_histogram, sma_signal, sharpe]):
        return None, None

    technical_score = 0.0
    weights = {}

    # ── RSI contribution: 0 to 2.5 points ───────────────────────────
    if rsi_value is not None:
        if rsi_value < RSI_OVERSOLD:
            rsi_points = 2.5
        elif rsi_value < 45:
            rsi_points = 1.5
        elif rsi_value > RSI_OVERBOUGHT:
            rsi_points = 0.0
        else:
            rsi_points = 1.0
        technical_score += rsi_points
        weights["rsi"] = rsi_points

    # ── MACD contribution: 0 to 2.5 points ──────────────────────────
    if macd_histogram is not None and macd_signal is not None:
        if macd_signal == MACDSignal.BULLISH and macd_histogram > 0:
            macd_points = 2.5 if macd_histogram > 0.5 else 1.5
        elif macd_signal == MACDSignal.BEARISH and macd_histogram < -0.5:
            macd_points = 0.0
        else:
            macd_points = 0.5
        technical_score += macd_points
        weights["macd"] = macd_points

    # ── SMA contribution: 0 to 2.5 points ───────────────────────────
    if sma_signal is not None:
        sma_points_map = {
            SMASignal.GOLDEN_CROSS: 2.5,
            SMASignal.ABOVE_200: 1.5,
            SMASignal.BELOW_200: 0.5,
            SMASignal.DEATH_CROSS: 0.0,
        }
        sma_points = sma_points_map.get(sma_signal, 0.5)
        technical_score += sma_points
        weights["sma"] = sma_points

    # ── Sharpe contribution: 0 to 2.5 points ────────────────────────
    if sharpe is not None:
        if sharpe > 1.5:
            sharpe_points = 2.5
        elif sharpe > 1.0:
            sharpe_points = 2.0
        elif sharpe > 0.5:
            sharpe_points = 1.0
        elif sharpe > 0:
            sharpe_points = 0.5
        else:
            sharpe_points = 0.0
        technical_score += sharpe_points
        weights["sharpe"] = sharpe_points

    # ── Blend technical + fundamental ───────────────────────────────
    if piotroski_score is not None:
        fundamental_score_10 = round(piotroski_score / 9 * 10, 2)
        composite = round(technical_score * 0.5 + fundamental_score_10 * 0.5, 2)
        weights["piotroski"] = piotroski_score
        weights["fundamental_score_10"] = fundamental_score_10
        weights["mode"] = "50/50"
    else:
        composite = round(technical_score, 2)
        weights["mode"] = "technical_only"

    weights["total"] = composite

    return composite, weights


# ─────────────────────────────────────────────────────────────────────────────
# Database persistence — store the computed signals
# ─────────────────────────────────────────────────────────────────────────────


async def store_signal_snapshot(
    result: SignalResult,
    db: AsyncSession,
    computed_at: datetime | None = None,
) -> None:
    """Store a SignalResult in the signal_snapshots hypertable.

    Uses ON CONFLICT DO UPDATE so that re-computing signals for the same
    ticker on the same day overwrites the previous snapshot.

    Args:
        result: The computed SignalResult to store.
        db: Async database session.
        computed_at: When the signals were computed. Defaults to now.
    """
    if computed_at is None:
        computed_at = datetime.now(timezone.utc)

    values = {
        "computed_at": computed_at,
        "ticker": result.ticker.upper(),
        "rsi_value": result.rsi_value,
        "rsi_signal": result.rsi_signal,
        "macd_value": result.macd_value,
        "macd_histogram": result.macd_histogram,
        "macd_signal_label": result.macd_signal_label,
        "sma_50": result.sma_50,
        "sma_200": result.sma_200,
        "sma_signal": result.sma_signal,
        "bb_upper": result.bb_upper,
        "bb_lower": result.bb_lower,
        "bb_position": result.bb_position,
        "annual_return": result.annual_return,
        "volatility": result.volatility,
        "sharpe_ratio": result.sharpe_ratio,
        "composite_score": result.composite_score,
        "composite_weights": result.composite_weights,
    }

    stmt = pg_insert(SignalSnapshot).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["computed_at", "ticker"],
        set_={k: v for k, v in values.items() if k not in ("computed_at", "ticker")},
    )

    await db.execute(stmt)
    await db.commit()

    logger.info(
        "Stored signal snapshot for %s (score=%.1f)", result.ticker, result.composite_score or 0
    )


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers — extracted from router inline queries
# ─────────────────────────────────────────────────────────────────────────────


async def get_latest_signals(ticker: str, db: AsyncSession) -> SignalSnapshot | None:
    """Fetch the most recent signal snapshot for a ticker.

    Args:
        ticker: Stock symbol (case-insensitive, uppercased internally).
        db: Async database session.

    Returns:
        The most recent SignalSnapshot, or None if no signals exist.
    """
    result = await db.execute(
        select(SignalSnapshot)
        .where(SignalSnapshot.ticker == ticker.upper())
        .order_by(SignalSnapshot.computed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_signal_history(
    ticker: str,
    db: AsyncSession,
    days: int = 90,
    limit: int = 100,
) -> list[SignalSnapshot]:
    """Fetch chronological signal snapshots for a ticker.

    Used for charting signal trends over time.

    Args:
        ticker: Stock symbol (case-insensitive, uppercased internally).
        db: Async database session.
        days: Number of days of history to return (default 90).
        limit: Maximum number of snapshots to return (default 100).

    Returns:
        List of SignalSnapshot objects ordered by computed_at ASC.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(SignalSnapshot)
        .where(SignalSnapshot.ticker == ticker.upper())
        .where(SignalSnapshot.computed_at >= cutoff)
        .order_by(SignalSnapshot.computed_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_bulk_signals(
    db: AsyncSession,
    *,
    index_id: str | None = None,
    tickers: list[str] | None = None,
    rsi_state: str | None = None,
    macd_state: str | None = None,
    sector: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    sharpe_min: float | None = None,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list]:
    """Fetch latest signals per ticker with filters and pagination (screener).

    Uses a row_number window function to get the most recent signal per ticker,
    then applies filters, sorting, and pagination.

    Args:
        db: Async database session.
        index_id: Optional index ID filter (e.g. "sp500").
        tickers: Optional list of tickers to filter by.
        rsi_state: Optional RSI signal filter (e.g. "OVERSOLD").
        macd_state: Optional MACD signal filter (e.g. "BULLISH").
        sector: Optional sector filter.
        score_min: Minimum composite score filter.
        score_max: Maximum composite score filter.
        sharpe_min: Minimum Sharpe ratio filter.
        sort_by: Field to sort by (default "composite_score").
        sort_order: Sort direction, "asc" or "desc" (default "desc").
        limit: Page size (default 50).
        offset: Page offset (default 0).

    Returns:
        Tuple of (total_count, rows) where rows are the query result rows
        with columns from SignalSnapshot + Stock.name + stock_sector + price_history.
    """
    # Latest signal per ticker using row_number window function
    latest = select(
        SignalSnapshot,
        Stock.name,
        Stock.sector.label("stock_sector"),
        func.row_number()
        .over(
            partition_by=SignalSnapshot.ticker,
            order_by=SignalSnapshot.computed_at.desc(),
        )
        .label("rn"),
    ).join(Stock, SignalSnapshot.ticker == Stock.ticker)

    # Apply ticker filter before subquery
    if tickers:
        latest = latest.where(SignalSnapshot.ticker.in_(tickers))

    # Apply index filter via join
    if index_id is not None:
        latest = latest.join(
            StockIndexMembership,
            Stock.ticker == StockIndexMembership.ticker,
        ).where(StockIndexMembership.index_id == index_id)

    latest = latest.subquery("latest")

    # Correlated subquery: last 30 adj_close values per ticker (chronological ASC)
    _last_30_times = (
        select(StockPrice.time)
        .where(StockPrice.ticker == latest.c.ticker)
        .order_by(StockPrice.time.desc())
        .limit(30)
        .correlate(latest)
        .subquery()
    )
    price_sub = (
        select(
            func.array_agg(
                aggregate_order_by(
                    StockPrice.adj_close.cast(Float),
                    StockPrice.time.asc(),
                )
            )
        )
        .where(StockPrice.ticker == latest.c.ticker)
        .where(StockPrice.time.in_(select(_last_30_times)))
        .correlate(latest)
        .scalar_subquery()
    )

    # Build main query filtering to rn=1 (most recent per ticker)
    query = select(latest, price_sub.label("price_history")).where(latest.c.rn == 1)

    # Apply filters
    if rsi_state is not None:
        query = query.where(latest.c.rsi_signal == rsi_state.upper())
    if macd_state is not None:
        query = query.where(latest.c.macd_signal_label == macd_state.upper())
    if sector is not None:
        query = query.where(latest.c.stock_sector == sector)
    if score_min is not None:
        query = query.where(latest.c.composite_score >= score_min)
    if score_max is not None:
        query = query.where(latest.c.composite_score <= score_max)
    if sharpe_min is not None:
        query = query.where(latest.c.sharpe_ratio >= sharpe_min)

    # Count total before pagination
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # Apply sorting (whitelist to prevent column enumeration)
    _ALLOWED_SORT = {
        "composite_score",
        "ticker",
        "rsi_value",
        "macd_value",
        "sma_50",
        "sma_200",
        "annual_return",
        "volatility",
        "sharpe_ratio",
        "stock_sector",
    }
    if sort_by not in _ALLOWED_SORT:
        sort_by = "composite_score"
    sort_column = getattr(latest.c, sort_by, latest.c.composite_score)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc().nulls_last())
    else:
        query = query.order_by(sort_column.desc().nulls_last())

    # Apply pagination
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    rows = result.all()

    return total, rows
