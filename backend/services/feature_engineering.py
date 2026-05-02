"""Vectorized technical indicator computation for ML feature engineering.

Pure functions — no DB access, no side effects. Takes pandas Series/DataFrames,
returns pandas Series/DataFrames. Used by backfill script and future nightly
feature assembly.

All indicators use the same parameters as backend/services/signals.py to ensure
consistency between live signal_snapshots and historical_features.
"""

from __future__ import annotations

import importlib.metadata  # noqa: F401 — pandas-ta-openbb needs this
import logging

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

# Match parameters from backend/services/signals.py exactly
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
SMA_SHORT = 50
SMA_LONG = 200
BB_PERIOD = 20
BB_STD_DEV = 2
TRADING_DAYS_PER_YEAR = 252

# Gate indicator parameters (confirmation-gate scoring v2)
ADX_PERIOD = 14
MFI_PERIOD = 14
OBV_SLOPE_WINDOW = 21


def compute_momentum(closes: pd.Series, window: int) -> pd.Series:
    """Compute N-day momentum (simple return).

    Args:
        closes: Adjusted closing prices with DatetimeIndex.
        window: Lookback period in trading days.

    Returns:
        Series of (price[t] / price[t-window]) - 1. NaN for first `window` rows.
    """
    return closes / closes.shift(window) - 1


def compute_rsi_series(closes: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Compute RSI for entire series (vectorized).

    Args:
        closes: Adjusted closing prices.
        period: RSI period (default 14).

    Returns:
        Series of RSI values (0-100). NaN for first `period` rows.
    """
    rsi = ta.rsi(closes, length=period)  # type: ignore[attr-defined]
    if rsi is None:
        return pd.Series(np.nan, index=closes.index)
    # pandas-ta Wilder's smoothing produces values earlier than the period
    # boundary; mask the warmup rows to match the expected NaN count.
    rsi.iloc[:period] = np.nan
    return rsi


def compute_macd_histogram_series(
    closes: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> pd.Series:
    """Compute MACD histogram for entire series (vectorized).

    Args:
        closes: Adjusted closing prices.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal line period (default 9).

    Returns:
        Series of MACD histogram values. NaN during warmup.
    """
    macd_df = ta.macd(closes, fast=fast, slow=slow, signal=signal)  # type: ignore[attr-defined]
    if macd_df is None:
        return pd.Series(np.nan, index=closes.index)
    hist_col = f"MACDh_{fast}_{slow}_{signal}"
    result: pd.Series = macd_df[hist_col]  # type: ignore[assignment]
    return result


def compute_sma_cross_series(closes: pd.Series) -> pd.Series:
    """Compute SMA cross encoding for entire series.

    Encoding (ordinal for tree models):
      2 = above BOTH SMA-50 and SMA-200 (strongest bullish)
      1 = above SMA-50 only (short-term bullish, long-term bearish)
      0 = below both SMA-50 and SMA-200 (bearish)

    Note: GOLDEN_CROSS/DEATH_CROSS transition events are collapsed into
    the ordinal. Consider adding a separate sma_cross_event feature in PR1
    for cross detection within a 5-day window.

    Args:
        closes: Adjusted closing prices.

    Returns:
        Series of integer codes (0, 1, 2). NaN until SMA-200 is available.
    """
    sma50 = ta.sma(closes, length=SMA_SHORT)  # type: ignore[attr-defined]
    sma200 = ta.sma(closes, length=SMA_LONG)  # type: ignore[attr-defined]

    if sma50 is None or sma200 is None:
        return pd.Series(np.nan, index=closes.index)

    result = pd.Series(np.nan, index=closes.index)

    valid = sma200.notna()
    above_both = (closes > sma50) & (closes > sma200) & valid
    above_50_only = (closes > sma50) & ~(closes > sma200) & valid
    below_both = valid & ~above_both & ~above_50_only

    result[above_both] = 2
    result[above_50_only] = 1
    result[below_both] = 0

    return result


def compute_bb_position_series(
    closes: pd.Series,
    period: int = BB_PERIOD,
    std: float = BB_STD_DEV,
) -> pd.Series:
    """Compute Bollinger Band position encoding for entire series.

    Encoding: UPPER=2, MIDDLE=1, LOWER=0.

    Args:
        closes: Adjusted closing prices.
        period: BB period (default 20).
        std: Number of standard deviations (default 2).

    Returns:
        Series of integer codes (0, 1, 2). NaN during warmup.
    """
    bb_df = ta.bbands(closes, length=period, std=std)  # type: ignore[attr-defined]
    if bb_df is None:
        return pd.Series(np.nan, index=closes.index)

    std_str = str(int(std)) if std == int(std) else str(std)
    upper_col = f"BBU_{period}_{std_str}"
    lower_col = f"BBL_{period}_{std_str}"

    upper = bb_df[upper_col]
    lower = bb_df[lower_col]

    result = pd.Series(np.nan, index=closes.index)
    valid = upper.notna()

    result[valid & (closes > upper)] = 2
    result[valid & (closes < lower)] = 0
    result[valid & (closes >= lower) & (closes <= upper)] = 1

    return result


def compute_volatility_series(
    closes: pd.Series,
    window: int = 30,
) -> pd.Series:
    """Compute rolling annualized volatility.

    Args:
        closes: Adjusted closing prices.
        window: Rolling window in trading days (default 30).

    Returns:
        Series of annualized volatility. NaN during warmup.
    """
    daily_returns = closes.pct_change()
    rolling_std = daily_returns.rolling(window=window).std()
    return rolling_std * np.sqrt(TRADING_DAYS_PER_YEAR)


def compute_sharpe_series(
    closes: pd.Series,
    window: int = 30,
) -> pd.Series:
    """Compute rolling Sharpe ratio (return / volatility).

    Uses risk_free_rate=0 intentionally: over a 10-year backfill the actual
    rate varied from 0% to 5%+. A constant rate biases the feature. Tree
    models learn splits (not coefficients), so the constant offset doesn't
    help — removing it eliminates the historical bias.

    Args:
        closes: Adjusted closing prices.
        window: Rolling window in trading days (default 30).

    Returns:
        Series of Sharpe ratios. NaN during warmup. Zero-vol days get 0.0
        (not NaN) to preserve them as training data.
    """
    daily_returns = closes.pct_change()
    rolling_mean = daily_returns.rolling(window=window).mean()
    rolling_std = daily_returns.rolling(window=window).std()

    ann_return = rolling_mean * TRADING_DAYS_PER_YEAR
    ann_vol = rolling_std * np.sqrt(TRADING_DAYS_PER_YEAR)

    sharpe = ann_return / ann_vol

    # Replace inf with 0.0 (happens when vol=0, meaning zero price movement
    # in the window — these are meaningful data points, not errors)
    sharpe = sharpe.replace([np.inf, -np.inf], 0.0)

    return sharpe


def compute_forward_log_returns(
    closes: pd.Series,
    horizon: int,
) -> pd.Series:
    """Compute forward N-day log returns (target variable for ML).

    Args:
        closes: Adjusted closing prices.
        horizon: Forward horizon in trading days.

    Returns:
        Series of ln(price[t+horizon] / price[t]). Last `horizon` rows are NaN.
    """
    future_prices = closes.shift(-horizon)
    return np.log(future_prices / closes)


def compute_adx_series(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = ADX_PERIOD
) -> pd.Series:
    """Compute ADX for entire series (vectorized).

    Args:
        high: High prices.
        low: Low prices.
        close: Closing prices.
        period: ADX period (default 14).

    Returns:
        Series of ADX values. NaN for warmup period.
    """
    adx_df = ta.adx(high, low, close, length=period)  # type: ignore[attr-defined]
    if adx_df is None or adx_df.empty:
        return pd.Series(np.nan, index=close.index)
    col = f"ADX_{period}"
    if col not in adx_df.columns:
        return pd.Series(np.nan, index=close.index)
    return pd.Series(adx_df[col])


def compute_obv_slope_series(
    close: pd.Series, volume: pd.Series, window: int = OBV_SLOPE_WINDOW
) -> pd.Series:
    """Compute rolling OBV slope (normalized) for entire series.

    Args:
        close: Closing prices.
        volume: Volume data.
        window: Rolling window for slope calculation (default 21).

    Returns:
        Series of normalized OBV slope values.
    """
    obv = ta.obv(close, volume)  # type: ignore[attr-defined]
    if obv is None:
        return pd.Series(np.nan, index=close.index)

    def _slope(arr: np.ndarray) -> float:
        if not np.isfinite(arr).any():
            return 0.0
        x = np.arange(len(arr), dtype=float)
        mean_abs = float(np.abs(arr).mean())
        if mean_abs == 0 or not np.isfinite(mean_abs):
            return 0.0
        try:
            slope = float(np.polyfit(x, arr, 1)[0])
        except (np.linalg.LinAlgError, ValueError):
            return 0.0
        return slope / mean_abs if np.isfinite(slope / mean_abs) else 0.0

    return pd.Series(obv.rolling(window).apply(_slope, raw=True))


def compute_mfi_series(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = MFI_PERIOD,
) -> pd.Series:
    """Compute MFI for entire series (vectorized).

    Args:
        high: High prices.
        low: Low prices.
        close: Closing prices.
        volume: Volume data.
        period: MFI period (default 14).

    Returns:
        Series of MFI values (0-100).
    """
    mfi = ta.mfi(high, low, close, volume, length=period)  # type: ignore[attr-defined]
    if mfi is None:
        return pd.Series(np.nan, index=close.index)
    return mfi


def build_feature_dataframe(
    closes: pd.Series,
    *,
    vix_closes: pd.Series,
    spy_closes: pd.Series,
) -> pd.DataFrame:
    """Build complete feature DataFrame for one ticker.

    Computes all 11 technical features + 4 NaN sentiment placeholders +
    2 NaN convergence placeholders + 2 forward return targets.
    Drops warmup rows where any technical feature is NaN (first ~200 rows
    due to SMA-200). Minimum input: 200+ price rows.

    Args:
        closes: Adjusted closing prices for the ticker.
        vix_closes: VIX closing prices (joined by date).
        spy_closes: SPY adjusted closing prices (for SPY momentum).

    Returns:
        DataFrame with 19 columns (11 tech + 4 sentiment + 2 convergence
        + 2 targets). Index is DatetimeIndex. Only rows with all 11 tech
        features present. Target columns may be NaN for the last 60-90 rows.
    """
    df = pd.DataFrame(index=closes.index)

    # 11 technical features
    df["momentum_21d"] = compute_momentum(closes, 21)
    df["momentum_63d"] = compute_momentum(closes, 63)
    df["momentum_126d"] = compute_momentum(closes, 126)
    df["rsi_value"] = compute_rsi_series(closes)
    df["macd_histogram"] = compute_macd_histogram_series(closes)
    df["sma_cross"] = compute_sma_cross_series(closes)
    df["bb_position"] = compute_bb_position_series(closes)
    df["volatility"] = compute_volatility_series(closes)
    df["sharpe_ratio"] = compute_sharpe_series(closes)

    # VIX: join by date (reindex to ticker's dates, forward-fill weekends)
    vix_aligned = vix_closes.reindex(closes.index, method="ffill")
    df["vix_level"] = vix_aligned

    # SPY momentum: compute 21d momentum on SPY, then join by date
    spy_mom = compute_momentum(spy_closes, 21)
    spy_mom_aligned = spy_mom.reindex(closes.index, method="ffill")
    df["spy_momentum_21d"] = spy_mom_aligned

    # 4 sentiment placeholders (NaN for historical backfill)
    df["stock_sentiment"] = np.nan
    df["sector_sentiment"] = np.nan
    df["macro_sentiment"] = np.nan
    df["sentiment_confidence"] = np.nan

    # Convergence placeholders (NaN for backfill — Phase 3 addition)
    df["signals_aligned"] = np.nan
    df["convergence_label"] = np.nan

    # 2 forward return targets
    df["forward_return_60d"] = compute_forward_log_returns(closes, 60)
    df["forward_return_90d"] = compute_forward_log_returns(closes, 90)

    # Drop warmup rows where ANY technical feature is NaN
    tech_cols = [
        "momentum_21d",
        "momentum_63d",
        "momentum_126d",
        "rsi_value",
        "macd_histogram",
        "sma_cross",
        "bb_position",
        "volatility",
        "sharpe_ratio",
        "vix_level",
        "spy_momentum_21d",
    ]
    df = df.dropna(subset=tech_cols)

    # Replace any remaining inf with 0.0 in numeric columns (defensive)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], 0.0)

    return df
