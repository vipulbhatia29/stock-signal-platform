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

import importlib.metadata  # noqa: F401 — pandas-ta-openbb maps.py needs this submodule loaded
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast

import numpy as np
import pandas as pd
import pandas_ta as ta
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

    # QuantStats per-stock metrics (vs SPY benchmark)
    sortino: float | None = None
    max_drawdown: float | None = None  # stored as positive (e.g. 0.15 = 15%)
    alpha: float | None = None
    beta: float | None = None
    data_days: int | None = None  # number of trading days used for QuantStats

    # Gate indicators (confirmation-gate scoring v2)
    adx_value: float | None = None
    obv_slope: float | None = None
    mfi_value: float | None = None
    atr_value: float | None = None
    piotroski_score_value: int | None = None
    macd_histogram_prev: float | None = None


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
    # Narrow to Series: df[col] is typed as DataFrame | Series by pandas stubs
    # even though for a single column it's always Series at runtime.
    closes = cast(pd.Series, df[close_col]).dropna()

    # Extract aligned OHLCV columns for gate indicator calculations.
    # Drop rows where ANY column is NaN to keep indexes aligned.
    # gate_closes is the close series from this aligned slice — use it
    # (not `closes`) when calling gate indicator functions so all inputs
    # share the same index.
    _ohlcv_cols = [c for c in ("High", "Low", "Volume") if c in df.columns]
    if _ohlcv_cols:
        _ohlcv = df[[close_col] + _ohlcv_cols].dropna()
        gate_closes = cast(pd.Series, _ohlcv[close_col])
        high = cast(pd.Series, _ohlcv["High"]) if "High" in _ohlcv.columns else None
        low = cast(pd.Series, _ohlcv["Low"]) if "Low" in _ohlcv.columns else None
        volume = cast(pd.Series, _ohlcv["Volume"]) if "Volume" in _ohlcv.columns else None
    else:
        gate_closes = closes
        high = None
        low = None
        volume = None

    # ── Guard: we need enough data to compute signals ────────────────────
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
            piotroski_score_value=piotroski_score,
        )

    # ── Compute each indicator ───────────────────────────────────────
    rsi_val, rsi_sig = compute_rsi(closes)
    macd_val, macd_hist, macd_sig, macd_hist_prev = compute_macd(closes)
    sma50, sma200, sma_sig = compute_sma(closes)
    bb_up, bb_low, bb_pos = compute_bollinger(closes)
    ann_ret, vol, sharpe = compute_risk_return(closes, risk_free_rate)

    # ── Compute gate indicators (OHLCV required) ──────────────────────
    adx_val = None
    obv_slope_val = None
    mfi_val = None
    atr_val = None

    if high is not None and low is not None:
        adx_val = compute_adx(high, low, gate_closes)
        atr_val = compute_atr(high, low, gate_closes)
    if volume is not None:
        obv_slope_val = compute_obv_slope(gate_closes, volume)
        if high is not None and low is not None:
            mfi_val = compute_mfi(high, low, gate_closes, volume)

    # ── Compute composite score ──────────────────────────────────────
    from backend.config import settings

    if settings.SIGNAL_SCORING_ENGINE == "confirmation_gate_v2":
        score, weights = compute_confirmation_gates(
            adx=adx_val,
            macd_histogram=macd_hist,
            macd_histogram_prev=macd_hist_prev,
            sma_50=sma50,
            sma_200=sma200,
            current_price=float(closes.iloc[-1]) if len(closes) > 0 else None,
            obv_slope=obv_slope_val,
            mfi=mfi_val,
            rsi=rsi_val,
            piotroski=piotroski_score,
        )
    else:
        # Fallback to additive v1 scoring (kill switch for rollback)
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
        adx_value=adx_val,
        obv_slope=obv_slope_val,
        mfi_value=mfi_val,
        atr_value=atr_val,
        piotroski_score_value=piotroski_score,
        macd_histogram_prev=macd_hist_prev,
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

    rsi_series = ta.rsi(closes, length=period)  # type: ignore[attr-defined]
    if rsi_series is None or rsi_series.dropna().empty:
        return None, None

    rsi_value = round(float(rsi_series.iloc[-1]), 2)

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
) -> tuple[float | None, float | None, str | None, float | None]:
    """Compute MACD (Moving Average Convergence Divergence).

    Args:
        closes: Series of closing prices.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal_period: Signal line EMA period (default 9).

    Returns:
        Tuple of (macd_value, histogram_value, signal_label, histogram_prev).
    """
    if len(closes) < slow + signal_period:
        return None, None, None, None

    macd_df = ta.macd(closes, fast=fast, slow=slow, signal=signal_period)  # type: ignore[attr-defined]
    if macd_df is None or macd_df.dropna().empty:
        return None, None, None, None

    macd_col = f"MACD_{fast}_{slow}_{signal_period}"
    hist_col = f"MACDh_{fast}_{slow}_{signal_period}"

    macd_val = round(float(macd_df[macd_col].iloc[-1]), 4)
    hist_val = round(float(macd_df[hist_col].iloc[-1]), 4)

    hist_prev = None
    hist_series = macd_df[hist_col].dropna()
    if len(hist_series) >= 2:
        hist_prev = round(float(hist_series.iloc[-2]), 4)

    signal = MACDSignal.BULLISH if hist_val > 0 else MACDSignal.BEARISH

    return macd_val, hist_val, signal, hist_prev


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
    sma_short = ta.sma(closes, length=short) if len(closes) >= short else None  # type: ignore[attr-defined]
    sma_long = ta.sma(closes, length=long) if len(closes) >= long else None  # type: ignore[attr-defined]

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

    bb_df = ta.bbands(closes, length=period, std=num_std)  # type: ignore[attr-defined]
    if bb_df is None or bb_df.dropna().empty:
        return None, None, None

    # pandas-ta-openbb uses integer std in column names (e.g. BBU_20_2 not BBU_20_2.0)
    std_str = str(int(num_std)) if num_std == int(num_std) else str(num_std)
    upper_col = f"BBU_{period}_{std_str}"
    lower_col = f"BBL_{period}_{std_str}"

    upper_val = round(float(bb_df[upper_col].iloc[-1]), 4)
    lower_val = round(float(bb_df[lower_col].iloc[-1]), 4)
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


ADX_PERIOD = 14  # 14-day ADX is standard
ATR_PERIOD = 14  # 14-day ATR is standard


def compute_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = ADX_PERIOD,
) -> float | None:
    """Compute ADX (Average Directional Index) — measures trend strength.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        period: Lookback period (default 14).

    Returns:
        ADX value (0-100), or None if insufficient data.
    """
    if len(high) < period + 1 or len(low) < period + 1 or len(close) < period + 1:
        return None

    adx_series = ta.adx(high, low, close, length=period)  # type: ignore[attr-defined]
    if adx_series is None or adx_series.dropna().empty:
        return None

    adx_col = f"ADX_{period}"
    adx_val = adx_series[adx_col].iloc[-1]
    if pd.isna(adx_val):
        return None

    return round(float(adx_val), 2)


def compute_obv_slope(
    closes: pd.Series,
    volumes: pd.Series,
    period: int = 21,
) -> float | None:
    """Compute OBV (On-Balance Volume) slope — measures volume trend.

    Computes linear regression slope of OBV over the lookback period.

    Args:
        closes: Series of closing prices.
        volumes: Series of volumes.
        period: Lookback period for slope calculation (default 20).

    Returns:
        OBV slope (normalized), or None if insufficient data.
    """
    if len(closes) < period + 1 or len(volumes) < period + 1:
        return None

    obv = ta.obv(closes, volumes)  # type: ignore[attr-defined]
    if obv is None or obv.dropna().empty:
        return None

    obv_values = obv.iloc[-period:]
    if len(obv_values) < period:
        return None

    x = np.arange(len(obv_values), dtype=float)
    y = obv_values.values.astype(float)
    if not np.isfinite(y).all():
        return None

    # Normalize slope by mean absolute OBV for cross-stock comparability
    mean_obv = np.abs(y).mean()
    if mean_obv == 0:
        return 0.0
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope / mean_obv, 6)


def compute_mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volumes: pd.Series,
    period: int = 14,
) -> float | None:
    """Compute MFI (Money Flow Index) — volume-weighted RSI.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        volumes: Series of volumes.
        period: Lookback period (default 14).

    Returns:
        MFI value (0-100), or None if insufficient data.
    """
    if (
        len(high) < period + 1
        or len(low) < period + 1
        or len(close) < period + 1
        or len(volumes) < period + 1
    ):
        return None

    mfi_series = ta.mfi(high, low, close, volumes, length=period)  # type: ignore[attr-defined]
    if mfi_series is None or mfi_series.dropna().empty:
        return None

    mfi_val = mfi_series.iloc[-1]
    if pd.isna(mfi_val):
        return None

    return round(float(mfi_val), 2)


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = ATR_PERIOD,
) -> float | None:
    """Compute ATR (Average True Range) — measures volatility.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        period: Lookback period (default 14).

    Returns:
        ATR value, or None if insufficient data.
    """
    if len(high) < period + 1 or len(low) < period + 1 or len(close) < period + 1:
        return None

    atr_series = ta.atr(high, low, close, length=period)  # type: ignore[attr-defined]
    if atr_series is None or atr_series.dropna().empty:
        return None

    atr_val = atr_series.iloc[-1]
    if pd.isna(atr_val):
        return None

    return round(float(atr_val), 4)


def compute_quantstats_stock(
    closes: pd.Series,
    spy_closes: pd.Series,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> dict:
    """Compute per-stock QuantStats metrics vs SPY benchmark.

    Args:
        closes: Daily closing prices for the stock.
        spy_closes: Daily closing prices for SPY (benchmark).
        risk_free_rate: Annual risk-free rate (default 4.5%).

    Returns:
        Dict with sortino, max_drawdown (positive), alpha, beta.
        All values are None when insufficient data (< 30 common trading days).
    """
    import quantstats as qs

    null_result: dict = {
        "sortino": None,
        "max_drawdown": None,
        "alpha": None,
        "beta": None,
        "data_days": 0,
    }

    returns = closes.pct_change().dropna()
    spy_returns = spy_closes.pct_change().dropna()
    # Normalize to tz-naive for intersection compatibility.
    # Series.index is typed as Index by pandas stubs; at runtime it's a
    # DatetimeIndex here because `closes` is price-keyed. Use isinstance
    # to narrow the type and satisfy pyright.
    if isinstance(returns.index, pd.DatetimeIndex) and returns.index.tz is not None:
        returns.index = returns.index.tz_localize(None)
    if isinstance(spy_returns.index, pd.DatetimeIndex) and spy_returns.index.tz is not None:
        spy_returns.index = spy_returns.index.tz_localize(None)
    common = returns.index.intersection(spy_returns.index)

    if len(common) < 30:
        null_result["data_days"] = len(common)
        return null_result

    # Subscripting with an Index broadens the stubbed return type; the
    # runtime value is always a Series here.
    returns = cast(pd.Series, returns[common])
    spy_returns = cast(pd.Series, spy_returns[common])

    try:
        import math

        def _safe(val: float, digits: int = 4) -> float | None:
            f = float(val)
            return round(f, digits) if math.isfinite(f) else None

        greeks = qs.stats.greeks(returns, spy_returns)
        greeks_dict = greeks.to_dict() if hasattr(greeks, "to_dict") else {}

        # QuantStats accepts Series at runtime; its stubs are strict about
        # parameter types so cast to float to satisfy pyright.
        return {
            "sortino": _safe(float(qs.stats.sortino(returns, rf=risk_free_rate))),
            "max_drawdown": _safe(float(abs(qs.stats.max_drawdown(returns)))),
            "alpha": _safe(greeks_dict.get("alpha", 0.0)),
            "beta": _safe(greeks_dict.get("beta", 0.0)),
            "data_days": len(common),
        }
    except Exception:
        logger.warning("QuantStats computation failed for stock, returning nulls", exc_info=True)
        return null_result


# ─────────────────────────────────────────────────────────────────────────────
# Composite score — combines all indicators into a single 0-10 number
# ─────────────────────────────────────────────────────────────────────────────


def _determine_direction(
    macd_histogram: float | None,
    sma_50: float | None,
    sma_200: float | None,
    current_price: float | None,
) -> str:
    """Determine overall direction from technical signals.

    Uses majority vote of available directional indicators:
    MACD histogram sign, SMA50 vs SMA200, price vs SMA50.

    Returns:
        "bullish" or "bearish".
    """
    bullish_votes = 0
    total_votes = 0

    if macd_histogram is not None:
        total_votes += 1
        if macd_histogram > 0:
            bullish_votes += 1

    if sma_50 is not None and sma_200 is not None:
        total_votes += 1
        if sma_50 > sma_200:
            bullish_votes += 1

    if current_price is not None and sma_50 is not None:
        total_votes += 1
        if current_price > sma_50:
            bullish_votes += 1

    if total_votes == 0:
        # Default bullish when no directional data available. This creates
        # a mild bullish bias for data-sparse tickers — Gates 3/4 will
        # evaluate against bullish expectations. Acceptable because: (1)
        # data-sparse = no MACD/SMA = Gates 2-4 likely skip anyway, (2)
        # the bias only affects Gate 4 RSI ranges when ADX IS available
        # but SMA/MACD are not — a rare edge case.
        return "bullish"

    return "bullish" if bullish_votes > total_votes / 2 else "bearish"


def compute_confirmation_gates(
    *,
    adx: float | None,
    macd_histogram: float | None,
    macd_histogram_prev: float | None,
    sma_50: float | None,
    sma_200: float | None,
    current_price: float | None,
    obv_slope: float | None,
    mfi: float | None,
    rsi: float | None,
    piotroski: int | None,
) -> tuple[float | None, dict | None]:
    """Compute composite score using 5-gate confirmation model.

    Each gate is binary (confirmed or not). Score = (confirmed/active) * 10.
    Gates with insufficient data are skipped (not counted as active).

    Gate 1: Trend regime (ADX > 20)
    Gate 2: Direction (MACD + SMA alignment, 3 of 4 conditions)
    Gate 3: Volume (OBV slope + MFI agree with direction)
    Gate 4: Entry timing (RSI in favorable zone, regime-aware)
    Gate 5: Fundamental health (Piotroski F-Score)

    Args:
        adx: ADX value (0-100). None = skip gate 1.
        macd_histogram: Current MACD histogram value.
        macd_histogram_prev: Prior day MACD histogram (for acceleration).
        sma_50: 50-day SMA value.
        sma_200: 200-day SMA value.
        current_price: Latest closing price.
        obv_slope: Normalized 21-day OBV slope.
        mfi: Money Flow Index (0-100).
        rsi: RSI value (0-100).
        piotroski: Piotroski F-Score (0-9). None = skip gate 5.

    Returns:
        Tuple of (composite_score, weights_dict). Both None if no gates evaluable.
    """
    # If nothing is available, return None
    if all(v is None for v in [adx, macd_histogram, rsi]):
        return None, None

    gates_active = 0
    gates_confirmed = 0
    weights: dict = {"mode": "confirmation_gate_v2"}

    # Determine overall direction from Gate 2 inputs (needed by Gates 3 and 4)
    direction = _determine_direction(macd_histogram, sma_50, sma_200, current_price)

    # ── Gate 1: Trend Regime (ADX) ────────────────────────────────────
    if adx is not None:
        gates_active += 1
        confirmed = adx > 20
        regime = "trending" if adx > 25 else ("emerging" if adx >= 20 else "range_bound")
        if confirmed:
            gates_confirmed += 1
        weights["gate_1_trend"] = {
            "confirmed": confirmed,
            "adx": adx,
            "regime": regime,
            "detail": (
                f"{'Strong' if adx > 25 else 'Emerging'} trend (ADX {adx})"
                if confirmed
                else f"Range-bound (ADX {adx})"
            ),
        }
    else:
        regime = "unknown"
        weights["gate_1_trend"] = {
            "confirmed": False,
            "adx": None,
            "regime": "unknown",
            "detail": "No ADX data",
        }

    # ── Gate 2: Direction (MACD + SMA alignment) ──────────────────────
    if (
        macd_histogram is not None
        and sma_50 is not None
        and sma_200 is not None
        and current_price is not None
    ):
        gates_active += 1
        conditions_met = 0
        conditions_total = 4

        # Condition 1: MACD histogram positive (bullish) or negative (bearish)
        macd_positive = macd_histogram > 0
        if direction == "bullish" and macd_positive:
            conditions_met += 1
        elif direction == "bearish" and not macd_positive:
            conditions_met += 1

        # Condition 2: MACD accelerating
        if macd_histogram_prev is not None:
            if direction == "bullish" and macd_histogram > macd_histogram_prev:
                conditions_met += 1
            elif direction == "bearish" and macd_histogram < macd_histogram_prev:
                conditions_met += 1
        else:
            conditions_total = 3  # Can't evaluate acceleration

        # Condition 3: Price above/below 50-day SMA
        if direction == "bullish" and current_price > sma_50:
            conditions_met += 1
        elif direction == "bearish" and current_price < sma_50:
            conditions_met += 1

        # Condition 4: 50-day SMA above/below 200-day SMA
        if direction == "bullish" and sma_50 > sma_200:
            conditions_met += 1
        elif direction == "bearish" and sma_50 < sma_200:
            conditions_met += 1

        confirmed = conditions_met >= 3 if conditions_total == 4 else conditions_met >= 2
        if confirmed:
            gates_confirmed += 1

        weights["gate_2_direction"] = {
            "confirmed": confirmed,
            "direction": direction,
            "conditions_met": conditions_met,
            "conditions_total": conditions_total,
            "macd_accel": macd_histogram_prev is not None
            and (
                (direction == "bullish" and macd_histogram > macd_histogram_prev)
                or (direction == "bearish" and macd_histogram < macd_histogram_prev)
            ),
            "sma_aligned": (direction == "bullish" and sma_50 > sma_200)
            or (direction == "bearish" and sma_50 < sma_200),
            "detail": (
                f"{direction.title()} — {conditions_met}/{conditions_total} direction signals align"
            ),
        }
    else:
        weights["gate_2_direction"] = {
            "confirmed": False,
            "direction": direction,
            "detail": "Insufficient data for direction",
        }

    # ── Gate 3: Volume Confirmation (OBV + MFI) ───────────────────────
    if obv_slope is not None and mfi is not None:
        gates_active += 1
        if direction == "bullish":
            obv_confirms = obv_slope > 0
            mfi_confirms = mfi > 50
        else:
            obv_confirms = obv_slope < 0
            mfi_confirms = mfi < 50

        confirmed = obv_confirms and mfi_confirms
        if confirmed:
            gates_confirmed += 1

        weights["gate_3_volume"] = {
            "confirmed": confirmed,
            "obv_slope": obv_slope,
            "mfi": mfi,
            "detail": (
                f"Money {'flowing in' if mfi > 50 else 'flowing out'} "
                f"(MFI {mfi}, OBV {'rising' if obv_slope > 0 else 'falling'})"
            ),
        }
    else:
        weights["gate_3_volume"] = {
            "confirmed": False,
            "obv_slope": obv_slope,
            "mfi": mfi,
            "detail": "Insufficient volume data",
        }

    # ── Gate 4: Entry Timing (RSI, regime-aware) ──────────────────────
    if rsi is not None:
        gates_active += 1
        confirmed = False

        if direction == "bullish":
            if regime == "trending" and 40 <= rsi <= 65:
                confirmed = True  # Pullback in uptrend
                detail = f"RSI {rsi} — pullback entry in uptrend (40-65)"
            elif regime == "range_bound" and rsi < 35:
                confirmed = True  # Oversold mean-reversion
                detail = f"RSI {rsi} — oversold mean-reversion entry (<35)"
            elif regime == "emerging" and rsi < 50:
                confirmed = True  # Not yet extended
                detail = f"RSI {rsi} — early trend entry (<50)"
            else:
                rsi_label = "chasing" if rsi > 65 else "unfavorable"
                detail = f"RSI {rsi} — {rsi_label} for {regime} {direction}"
        else:  # bearish
            if regime == "trending" and 35 <= rsi <= 60:
                confirmed = True
                detail = f"RSI {rsi} — bounce entry in downtrend (35-60)"
            elif regime == "range_bound" and rsi > 65:
                confirmed = True
                detail = f"RSI {rsi} — overbought mean-reversion entry (>65)"
            elif regime == "emerging" and rsi > 50:
                confirmed = True
                detail = f"RSI {rsi} — early downtrend entry (>50)"
            else:
                detail = f"RSI {rsi} — unfavorable for {regime} {direction}"

        if confirmed:
            gates_confirmed += 1

        weights["gate_4_entry"] = {
            "confirmed": confirmed,
            "rsi": rsi,
            "regime": regime,
            "detail": detail,
        }
    else:
        weights["gate_4_entry"] = {
            "confirmed": False,
            "rsi": None,
            "detail": "No RSI data",
        }

    # ── Gate 5: Fundamental Health (Piotroski) ────────────────────────
    # Piotroski 4-6 is truly neutral — gate is NOT counted as active.
    # Only strong (>=7, confirms) and weak (0-3, vetoes) are active.
    if piotroski is not None:
        if piotroski >= 7:
            gates_active += 1
            gates_confirmed += 1
            confirmed = True
            detail = f"Strong fundamentals (F-Score {piotroski}/9)"
        elif piotroski >= 4:
            # Neutral — gate not counted as active
            confirmed = False
            detail = f"Neutral fundamentals (F-Score {piotroski}/9) — no effect"
        else:
            gates_active += 1
            confirmed = False  # Weak — vetoes bullish
            detail = f"Weak fundamentals (F-Score {piotroski}/9) — vetoes bullish"

        weights["gate_5_fundamental"] = {
            "confirmed": confirmed,
            "piotroski": piotroski,
            "detail": detail,
        }
    else:
        weights["gate_5_fundamental"] = {
            "confirmed": False,
            "piotroski": None,
            "detail": "No fundamental data (skipped)",
        }

    # ── Compute final score ───────────────────────────────────────────
    if gates_active == 0:
        return None, None

    score = round((gates_confirmed / gates_active) * 10, 1)
    weights["gates_active"] = gates_active
    weights["gates_confirmed"] = gates_confirmed
    weights["total"] = score

    return score, weights


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
        "change_pct": result.change_pct,
        "current_price": result.current_price,
        "sortino": result.sortino,
        "max_drawdown": result.max_drawdown,
        "alpha": result.alpha,
        "beta": result.beta,
        "data_days": result.data_days,
        "adx_value": result.adx_value,
        "obv_slope": result.obv_slope,
        "mfi_value": result.mfi_value,
        "atr_value": result.atr_value,
        "piotroski_score": result.piotroski_score_value,
        "macd_histogram_prev": result.macd_histogram_prev,
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
        "current_price",
        "change_pct",
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
    rows = list(result.all())

    return total, rows
