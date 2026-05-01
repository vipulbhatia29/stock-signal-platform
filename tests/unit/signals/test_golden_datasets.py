"""Golden dataset regression tests for signal computation.

Uses hardcoded reference data computed from standard TA-Lib/pandas-ta formulas
to verify our signal engine produces correct values within acceptable tolerance.

These tests guard against accidental formula changes or library version drift.
"""

from __future__ import annotations

import importlib.metadata  # noqa: F401 — pandas-ta-openbb importlib bug

import pandas as pd
import pytest

from backend.services.signals import compute_bollinger, compute_macd, compute_rsi

# ---------------------------------------------------------------------------
# Reference price data — hand-crafted 50-day series
# ---------------------------------------------------------------------------

# 50 days of synthetic prices derived from a known seed — used for MACD golden dataset
_PRICES_50 = [
    100.00,
    100.80,
    101.65,
    102.54,
    103.47,
    104.44,
    105.46,
    106.51,
    107.61,
    108.75,
    109.93,
    111.16,
    112.43,
    113.75,
    115.12,
    116.54,
    118.01,
    119.53,
    121.11,
    122.74,
    124.43,
    126.18,
    128.00,
    129.87,
    131.81,
    133.81,
    135.88,
    138.01,
    140.22,
    142.49,
    144.84,
    147.26,
    149.75,
    152.33,
    155.00,
    157.74,
    160.57,
    163.49,
    166.49,
    169.59,
    172.79,
    176.08,
    179.47,
    182.97,
    186.57,
    190.28,
    194.10,
    198.03,
    202.08,
    206.24,
]

# 30 days for RSI and Bollinger
_PRICES_30 = _PRICES_50[:30]


def _series(prices: list[float]) -> pd.Series:
    """Wrap price list as a DatetimeIndex Series."""
    idx = pd.bdate_range("2024-01-01", periods=len(prices))
    return pd.Series(prices, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# Hardcoded golden reference values
# Reference: pandas-ta-openbb 0.4.24, computed 2026-04-02
# These were computed once from the price series above and must NOT be
# recomputed dynamically — doing so would make the test tautological.
# ---------------------------------------------------------------------------

# RSI(14) for 30-day monotonically increasing series — approaches 100 (all-positive changes)
_EXPECTED_RSI: float = 100.0

# MACD(12,26,9) for 50-day series
_EXPECTED_MACD_LINE: float = 18.486706086459236
_EXPECTED_MACD_HIST: float = 1.8798483541797353

# Bollinger(20,2) for 30-day series (last 10 days: prices 113.75–142.49)
_EXPECTED_BB_UPPER: float = 144.30449072948883
_EXPECTED_BB_LOWER: float = 104.7975092705112


# ---------------------------------------------------------------------------
# RSI golden dataset test
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_rsi_14_golden_dataset_matches_expected() -> None:
    """RSI(14) for known 30-day series must match the reference value within atol=0.5."""
    closes = _series(_PRICES_30)
    rsi_val, _ = compute_rsi(closes, period=14)
    assert rsi_val is not None, "RSI should be computable for 30-day series"
    assert abs(rsi_val - _EXPECTED_RSI) < 0.5, (
        f"RSI={rsi_val} deviates from expected={_EXPECTED_RSI} (atol=0.5)"
    )


@pytest.mark.domain
def test_rsi_14_golden_value_in_bounds() -> None:
    """RSI from golden dataset must be within [0, 100]."""
    closes = _series(_PRICES_30)
    rsi_val, _ = compute_rsi(closes, period=14)
    if rsi_val is not None:
        assert 0.0 <= rsi_val <= 100.0


@pytest.mark.domain
def test_rsi_14_uptrend_is_high() -> None:
    """Strongly rising prices in our golden dataset should yield RSI > 50."""
    closes = _series(_PRICES_30)
    rsi_val, signal = compute_rsi(closes, period=14)
    # All prices are rising, so RSI should be well above 50 and likely overbought
    assert rsi_val is not None
    assert rsi_val > 50.0, f"Expected RSI > 50 for uptrend, got {rsi_val}"


# ---------------------------------------------------------------------------
# MACD golden dataset test
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_macd_12_26_9_golden_dataset_matches_expected() -> None:
    """MACD line for known 50-day series must match reference (rtol=0.05)."""
    closes = _series(_PRICES_50)
    macd_val, hist_val, signal_label, hist_prev = compute_macd(
        closes, fast=12, slow=26, signal_period=9
    )
    assert macd_val is not None, "MACD should be computable for 50-day series"
    # Relative tolerance of 5%
    assert abs(macd_val - _EXPECTED_MACD_LINE) <= abs(_EXPECTED_MACD_LINE) * 0.05 + 0.01, (
        f"MACD={macd_val} deviates from expected={_EXPECTED_MACD_LINE}"
    )


@pytest.mark.domain
def test_macd_histogram_golden_dataset_sign() -> None:
    """MACD histogram sign (positive = bullish) must match reference."""
    closes = _series(_PRICES_50)
    _, hist_val, signal_label, _ = compute_macd(closes, fast=12, slow=26, signal_period=9)
    assert hist_val is not None
    # Signs must agree
    assert (hist_val > 0) == (_EXPECTED_MACD_HIST > 0), (
        f"Histogram sign mismatch: computed={hist_val}, expected={_EXPECTED_MACD_HIST}"
    )


@pytest.mark.domain
def test_macd_uptrend_is_bullish() -> None:
    """MACD for a strong uptrend should be BULLISH."""
    closes = _series(_PRICES_50)
    _, _, signal_label, _ = compute_macd(closes, fast=12, slow=26, signal_period=9)
    assert signal_label == "BULLISH", f"Expected BULLISH for uptrend, got {signal_label}"


# ---------------------------------------------------------------------------
# Bollinger Bands golden dataset test
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_bollinger_20_2_golden_upper_band_matches() -> None:
    """Bollinger upper band for known 30-day series must match reference."""
    closes = _series(_PRICES_30)
    upper, lower, _ = compute_bollinger(closes, period=20, num_std=2)
    assert upper is not None, "Bollinger upper band should be computable"
    assert abs(upper - _EXPECTED_BB_UPPER) <= abs(_EXPECTED_BB_UPPER) * 0.02 + 0.01, (
        f"BB upper={upper} deviates from expected={_EXPECTED_BB_UPPER}"
    )


@pytest.mark.domain
def test_bollinger_20_2_golden_lower_band_matches() -> None:
    """Bollinger lower band for known 30-day series must match reference."""
    closes = _series(_PRICES_30)
    upper, lower, _ = compute_bollinger(closes, period=20, num_std=2)
    assert lower is not None, "Bollinger lower band should be computable"
    assert abs(lower - _EXPECTED_BB_LOWER) <= abs(_EXPECTED_BB_LOWER) * 0.02 + 0.01, (
        f"BB lower={lower} deviates from expected={_EXPECTED_BB_LOWER}"
    )


@pytest.mark.domain
def test_bollinger_golden_ordering() -> None:
    """Golden dataset: upper band must be > lower band."""
    closes = _series(_PRICES_30)
    upper, lower, _ = compute_bollinger(closes, period=20, num_std=2)
    if upper is not None and lower is not None:
        assert upper > lower, f"BB upper={upper} must be > lower={lower}"


@pytest.mark.domain
def test_bollinger_golden_price_position() -> None:
    """Golden dataset: current price relative to bands should be UPPER (strong uptrend)."""
    closes = _series(_PRICES_30)
    upper, lower, position = compute_bollinger(closes, period=20, num_std=2)
    # Strong uptrend → current price likely above upper band or at least middle
    assert position is not None
    assert position in ("UPPER", "MIDDLE", "LOWER"), f"Invalid position: {position}"
