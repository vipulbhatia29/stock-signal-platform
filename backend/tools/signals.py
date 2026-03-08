"""Signal computation tool — technical indicators and composite scoring.

This is the brain of the platform. It takes raw price data (OHLCV) and
computes technical analysis indicators that tell us whether a stock looks
like a good buy, hold, or sell.

Technical Analysis 101 (for learning):
────────────────────────────────────────
Technical analysis looks at price/volume patterns to predict future moves.
It's based on the idea that price trends tend to continue, and that certain
patterns repeat. Here are the indicators we compute:

1. RSI (Relative Strength Index) — Measures momentum (0-100 scale)
   - Below 30 = "oversold" → stock may be undervalued, potential BUY
   - Above 70 = "overbought" → stock may be overvalued, potential SELL
   - Between 30-70 = "neutral" → no strong signal

2. MACD (Moving Average Convergence Divergence) — Trend direction
   - When MACD histogram > 0 and rising → bullish (uptrend)
   - When MACD histogram < 0 and falling → bearish (downtrend)

3. SMA (Simple Moving Average) — Long-term trend
   - "Golden Cross" = 50-day SMA crosses above 200-day → BULLISH
   - "Death Cross" = 50-day SMA crosses below 200-day → BEARISH

4. Bollinger Bands — Volatility boundaries
   - Price above upper band → potentially overbought
   - Price below lower band → potentially oversold

5. Sharpe Ratio — Risk-adjusted return
   - Higher is better: >1.0 is good, >1.5 is excellent
   - Tells you how much return you're getting per unit of risk

Composite Score (0-10):
   Each indicator contributes 0-2.5 points. A score of 8+ = strong buy signal.
   Score 5-7 = watch. Score below 5 = avoid.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.signal import SignalSnapshot

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


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point — compute all signals for a ticker
# ─────────────────────────────────────────────────────────────────────────────
def compute_signals(
    ticker: str,
    df: pd.DataFrame,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
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

    Returns:
        A SignalResult dataclass with all indicator values and labels.
    """
    # ── Determine which price column to use ──────────────────────────
    # "Adj Close" (adjusted close) accounts for stock splits and dividends.
    # It's the "true" price for calculations. Fall back to "Close" if
    # "Adj Close" isn't available.
    close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    closes = df[close_col].dropna()

    # ── Guard: we need enough data to compute signals ────────────────
    # RSI needs 14+ days, MACD needs 26+ days, SMA needs 200+ days.
    # If we don't have enough data, return None for the indicators that
    # can't be computed.
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
    )

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
    )


# ─────────────────────────────────────────────────────────────────────────────
# Individual indicator calculations
# ─────────────────────────────────────────────────────────────────────────────


def compute_rsi(closes: pd.Series, period: int = RSI_PERIOD) -> tuple[float | None, str | None]:
    """Compute the RSI (Relative Strength Index).

    RSI measures how fast and how much a stock's price is changing.
    It oscillates between 0 and 100.

    The algorithm (Wilder's smoothed method):
      1. Calculate daily price changes (today's close - yesterday's close)
      2. Separate gains (positive changes) and losses (negative changes)
      3. Calculate the average gain and average loss over 'period' days
      4. RS = average_gain / average_loss
      5. RSI = 100 - (100 / (1 + RS))

    Why Wilder's smoothing? It uses an exponential moving average instead
    of a simple average, giving more weight to recent data while still
    considering the full history.

    Args:
        closes: Series of closing prices.
        period: Lookback period (default 14 days).

    Returns:
        Tuple of (rsi_value, signal_label).
        rsi_value is 0-100; signal_label is OVERSOLD/NEUTRAL/OVERBOUGHT.
    """
    if len(closes) < period + 1:
        return None, None

    # Calculate daily price changes: today - yesterday
    delta = closes.diff()

    # Separate into gains (positive changes) and losses (negative → positive)
    gains = delta.clip(lower=0)  # Keep only positive values, zeros otherwise
    losses = (-delta).clip(lower=0)  # Flip negatives to positive, zeros otherwise

    # Wilder's smoothed moving average — uses exponential weighting.
    # com = period - 1 makes the EMA equivalent to Wilder's smoothing.
    # min_periods = period ensures we have enough data before computing.
    avg_gain = gains.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = losses.ewm(com=period - 1, min_periods=period).mean()

    # RS = relative strength = average gain / average loss
    # When avg_loss is 0, RS is infinite → RSI = 100 (maximum bullishness)
    rs = avg_gain / avg_loss

    # RSI formula: converts RS to a 0-100 scale
    rsi = 100 - (100 / (1 + rs))

    # Get the most recent RSI value
    rsi_value = round(float(rsi.iloc[-1]), 2)

    # Assign a human-readable signal label
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

    MACD shows the relationship between two moving averages of a stock's price.
    It helps identify trend direction and momentum.

    The algorithm:
      1. Calculate the 12-day EMA (Exponential Moving Average) — "fast line"
      2. Calculate the 26-day EMA — "slow line"
      3. MACD line = fast EMA - slow EMA
      4. Signal line = 9-day EMA of the MACD line
      5. Histogram = MACD line - Signal line

    How to read it:
      - Histogram > 0 → the fast EMA is above the slow EMA → bullish momentum
      - Histogram < 0 → the fast EMA is below the slow EMA → bearish momentum
      - Histogram crossing from negative to positive → potential buy signal
      - Histogram crossing from positive to negative → potential sell signal

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

    # EMA = Exponential Moving Average — gives more weight to recent prices
    # than a Simple Moving Average (SMA) does. This makes it more responsive
    # to recent price changes.
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()

    # MACD line = fast EMA - slow EMA
    # When fast > slow, the stock has positive short-term momentum
    macd_line = ema_fast - ema_slow

    # Signal line = 9-day EMA of the MACD line itself
    # This smooths out the MACD and helps identify turning points
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

    # Histogram = MACD - Signal
    # This is the most actionable part — it shows momentum direction
    histogram = macd_line - signal_line

    macd_val = round(float(macd_line.iloc[-1]), 4)
    hist_val = round(float(histogram.iloc[-1]), 4)

    # Label: is the histogram positive (bullish) or negative (bearish)?
    signal = MACDSignal.BULLISH if hist_val > 0 else MACDSignal.BEARISH

    return macd_val, hist_val, signal


def compute_sma(
    closes: pd.Series,
    short: int = SMA_SHORT,
    long: int = SMA_LONG,
) -> tuple[float | None, float | None, str | None]:
    """Compute Simple Moving Averages and detect crossover signals.

    A Simple Moving Average (SMA) is the average closing price over the
    last N days. We use two:
      - SMA(50): short-term trend (last ~2.5 months)
      - SMA(200): long-term trend (last ~10 months)

    The "Golden Cross" and "Death Cross" are famous signals:
      - Golden Cross: 50-day SMA crosses ABOVE 200-day → BUY signal
      - Death Cross: 50-day SMA crosses BELOW 200-day → SELL signal

    We check for crossovers by comparing today vs yesterday:
      - If SMA50 was below SMA200 yesterday but above today → Golden Cross
      - If SMA50 was above SMA200 yesterday but below today → Death Cross

    Args:
        closes: Series of closing prices.
        short: Short-term SMA period (default 50).
        long: Long-term SMA period (default 200).

    Returns:
        Tuple of (sma_50_value, sma_200_value, signal_label).
    """
    sma_short = closes.rolling(window=short).mean() if len(closes) >= short else None
    sma_long = closes.rolling(window=long).mean() if len(closes) >= long else None

    # Extract latest values
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

    # ── Determine the signal label ───────────────────────────────────
    if sma_short is None or sma_long is None or sma50_val is None or sma200_val is None:
        # Not enough data for both SMAs
        return sma50_val, sma200_val, None

    # Check for crossover (comparing last 2 days)
    if len(sma_short) >= 2 and len(sma_long) >= 2:
        today_short = sma_short.iloc[-1]
        today_long = sma_long.iloc[-1]
        yesterday_short = sma_short.iloc[-2]
        yesterday_long = sma_long.iloc[-2]

        # Golden Cross: SMA50 was below SMA200 yesterday, now above today
        if yesterday_short <= yesterday_long and today_short > today_long:
            return sma50_val, sma200_val, SMASignal.GOLDEN_CROSS

        # Death Cross: SMA50 was above SMA200 yesterday, now below today
        if yesterday_short >= yesterday_long and today_short < today_long:
            return sma50_val, sma200_val, SMASignal.DEATH_CROSS

    # No crossover — check if price is above or below the 200-day SMA
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

    Bollinger Bands create a "channel" around the stock price:
      - Middle band = 20-day SMA (the average price)
      - Upper band = Middle + 2 × standard deviation
      - Lower band = Middle - 2 × standard deviation

    The idea: ~95% of price action should fall within the bands.
    When price breaks outside:
      - Above upper band → stock may be overbought (stretched too high)
      - Below lower band → stock may be oversold (stretched too low)

    Standard deviation measures how spread out the prices are. High StdDev
    means more volatile (wider bands), low StdDev means less volatile
    (narrower bands).

    Args:
        closes: Series of closing prices.
        period: Lookback period for the moving average (default 20).
        num_std: Number of standard deviations for band width (default 2).

    Returns:
        Tuple of (upper_band, lower_band, position_label).
    """
    if len(closes) < period:
        return None, None, None

    # Middle band = simple moving average over 'period' days
    sma = closes.rolling(window=period).mean()

    # Standard deviation over the same period
    std = closes.rolling(window=period).std()

    # Upper and lower bands: mean ± (num_std × standard deviation)
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)

    upper_val = round(float(upper.iloc[-1]), 4)
    lower_val = round(float(lower.iloc[-1]), 4)
    current_price = float(closes.iloc[-1])

    # Determine where the current price sits relative to the bands
    if current_price > upper_val:
        position = BBSignal.UPPER  # Above upper band → potentially overbought
    elif current_price < lower_val:
        position = BBSignal.LOWER  # Below lower band → potentially oversold
    else:
        position = BBSignal.MIDDLE  # Between bands → normal range

    return upper_val, lower_val, position


def compute_risk_return(
    closes: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> tuple[float | None, float | None, float | None]:
    """Compute annualized return, volatility, and Sharpe ratio.

    These metrics help you understand the risk/reward profile of a stock:

    1. Annualized Return: How much the stock gained per year.
       Formula: (latest_price / earliest_price) ^ (252 / trading_days) - 1
       Example: If a stock went from $100 to $150 in 1 year → 50% return

    2. Volatility: How much the stock's price bounces around.
       Formula: std(daily_returns) × √252
       The √252 converts daily volatility to annual. Higher = more risky.
       Example: 20% volatility means you can roughly expect ±20% swings/year

    3. Sharpe Ratio: Return per unit of risk.
       Formula: (annualized_return - risk_free_rate) / volatility
       The risk-free rate is what you'd earn from a safe investment (T-bills).
       Sharpe > 1.0 is good, > 1.5 is very good, > 2.0 is excellent.
       If Sharpe is negative, you'd be better off in Treasury bills!

    Args:
        closes: Series of closing prices.
        risk_free_rate: Annual risk-free rate (default 4.5%).

    Returns:
        Tuple of (annualized_return, volatility, sharpe_ratio).
    """
    if len(closes) < 2:
        return None, None, None

    # ── Daily returns ────────────────────────────────────────────────
    # pct_change() calculates (today - yesterday) / yesterday for each day.
    # This gives us the daily percentage change. We drop NaN (first row).
    daily_returns = closes.pct_change().dropna()

    if len(daily_returns) < 1:
        return None, None, None

    trading_days = len(daily_returns)

    # ── Annualized return ────────────────────────────────────────────
    # We use the geometric method: (end_price / start_price) ^ (252/days) - 1
    # This accounts for compounding, which a simple average doesn't.
    total_return = float(closes.iloc[-1]) / float(closes.iloc[0])
    annualized = total_return ** (TRADING_DAYS_PER_YEAR / trading_days) - 1
    annualized = round(annualized, 4)

    # ── Annualized volatility ────────────────────────────────────────
    # std() of daily returns gives daily volatility.
    # Multiply by √252 to annualize (variance scales linearly with time,
    # so standard deviation scales with √time).
    daily_vol = float(daily_returns.std())
    vol = round(daily_vol * np.sqrt(TRADING_DAYS_PER_YEAR), 4)

    # ── Sharpe ratio ─────────────────────────────────────────────────
    # (return - risk_free) / volatility
    # If volatility is 0 (stock never moved), Sharpe is undefined.
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
) -> tuple[float | None, dict | None]:
    """Compute the composite score (0-10) from individual signal values.

    The composite score boils down all our technical indicators into one
    number that's easy to act on:
      - 8-10: Strong BUY signal
      - 5-7:  WATCH (monitor closely)
      - 0-4:  AVOID (weak technicals)

    Each indicator contributes up to 2.5 points (4 indicators × 2.5 = 10 max).

    Phase 1 uses 100% technical weights. In Phase 3, we'll add fundamental
    analysis (P/E ratio, Piotroski score, etc.) and split the weight 50/50.

    The weights dict records exactly how many points each indicator
    contributed, which is stored in the database for transparency.

    Args:
        rsi_value: RSI numeric value (0-100).
        rsi_signal: RSI label (OVERSOLD/NEUTRAL/OVERBOUGHT).
        macd_histogram: MACD histogram value.
        macd_signal: MACD label (BULLISH/BEARISH).
        sma_signal: SMA label (GOLDEN_CROSS/DEATH_CROSS/ABOVE_200/BELOW_200).
        sharpe: Sharpe ratio value.

    Returns:
        Tuple of (composite_score, weights_dict).
        weights_dict shows the point breakdown, e.g. {"rsi": 2.5, "macd": 1.5, ...}
    """
    # If we don't have enough data for any indicator, we can't score
    if all(v is None for v in [rsi_value, macd_histogram, sma_signal, sharpe]):
        return None, None

    score = 0.0
    weights = {}

    # ── RSI contribution: 0 to 2.5 points ───────────────────────────
    # Oversold stocks get the highest score because they may be undervalued
    # (contrarian signal — buy when others are selling).
    if rsi_value is not None:
        if rsi_value < RSI_OVERSOLD:
            rsi_points = 2.5  # Oversold → strong buying opportunity
        elif rsi_value < 45:
            rsi_points = 1.5  # Slightly below neutral → moderate opportunity
        elif rsi_value > RSI_OVERBOUGHT:
            rsi_points = 0.0  # Overbought → risky to buy now
        else:
            rsi_points = 1.0  # Neutral zone
        score += rsi_points
        weights["rsi"] = rsi_points

    # ── MACD contribution: 0 to 2.5 points ──────────────────────────
    # Positive and increasing histogram = strong upward momentum.
    if macd_histogram is not None and macd_signal is not None:
        if macd_signal == MACDSignal.BULLISH and macd_histogram > 0:
            # Check if histogram is increasing (comparing last 2 values isn't
            # available here since we only get the latest value — we use the
            # histogram value magnitude as a proxy for strength).
            macd_points = 2.5 if macd_histogram > 0.5 else 1.5
        elif macd_signal == MACDSignal.BEARISH and macd_histogram < -0.5:
            macd_points = 0.0  # Strong bearish momentum
        else:
            macd_points = 0.5  # Weak or transitional
        score += macd_points
        weights["macd"] = macd_points

    # ── SMA contribution: 0 to 2.5 points ───────────────────────────
    # Golden Cross is the strongest bullish signal in SMA analysis.
    if sma_signal is not None:
        sma_points_map = {
            SMASignal.GOLDEN_CROSS: 2.5,  # 50-day crossed above 200-day
            SMASignal.ABOVE_200: 1.5,  # Price above long-term trend
            SMASignal.BELOW_200: 0.5,  # Price below long-term trend
            SMASignal.DEATH_CROSS: 0.0,  # 50-day crossed below 200-day
        }
        sma_points = sma_points_map.get(sma_signal, 0.5)
        score += sma_points
        weights["sma"] = sma_points

    # ── Sharpe contribution: 0 to 2.5 points ────────────────────────
    # Higher Sharpe = better risk-adjusted returns.
    if sharpe is not None:
        if sharpe > 1.5:
            sharpe_points = 2.5  # Excellent risk-adjusted return
        elif sharpe > 1.0:
            sharpe_points = 2.0  # Very good
        elif sharpe > 0.5:
            sharpe_points = 1.0  # Decent
        elif sharpe > 0:
            sharpe_points = 0.5  # Positive but low
        else:
            sharpe_points = 0.0  # Negative → losing money after risk adjustment
        score += sharpe_points
        weights["sharpe"] = sharpe_points

    composite = round(score, 2)
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

    Each time we compute signals for a ticker, we save a snapshot so we
    can track how signals change over time. This is stored in a
    TimescaleDB hypertable for efficient time-range queries.

    Uses ON CONFLICT DO UPDATE so that re-computing signals for the same
    ticker on the same day overwrites the previous snapshot rather than
    creating a duplicate.

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

    # Upsert: insert or update if (computed_at, ticker) already exists.
    # This is important because if we run signal computation twice on
    # the same day, we want to update rather than create a duplicate.
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
