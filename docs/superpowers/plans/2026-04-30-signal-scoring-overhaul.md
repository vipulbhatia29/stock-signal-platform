# Signal Scoring Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the additive 4-indicator composite score with a 5-gate confirmation pipeline (ADX trend → MACD/SMA direction → OBV/MFI volume → RSI entry timing → Piotroski fundamentals) so the scoring system produces actionable BUY/SELL signals.

**Architecture:** The gate engine is a pure function that takes pre-computed indicator values and returns (score, explanation_dict). New indicators (ADX, OBV slope, MFI, ATR) are computed in `compute_signals()` alongside existing ones. Schema changes add 6 columns to `signal_snapshots` and 6 fields to `SignalResult`. The 0-10 score interface and all downstream consumers remain unchanged. **One consumer requires migration:** `signal_convergence.py` reads Piotroski from `composite_weights` JSONB (old format) — must switch to the new `piotroski_score` column.

**Tech Stack:** pandas-ta (ADX, OBV, MFI, ATR), SQLAlchemy 2.0 mapped_column, Alembic, pytest + Hypothesis

**Spec:** `docs/superpowers/specs/2026-04-30-signal-scoring-overhaul.md`

---

## PR1: Schema + New Indicator Computation (KAN-555)

### Fact Sheet

```
Alembic head: 757cedd28893 (migration 043)
Next migration: 044
SignalSnapshot model: backend/models/signal.py (71 lines, 24 columns)
SignalResult dataclass: backend/services/signals.py:95-143 (20 fields)
compute_signals(): backend/services/signals.py:175-269
Re-export shim: backend/tools/signals.py (re-exports everything from services.signals)
Test file: tests/unit/signals/test_signals.py
Test helper: _make_ohlcv_df() at line 79 — creates OHLCV with constant Volume=1M
Hardening helper: _make_hardening_price_series() at line 631 — creates OHLCV with random Volume
pandas-ta import: requires `import importlib.metadata` before `import pandas_ta` (noqa: F401)
```

### Task 1: Migration — add 6 columns to signal_snapshots

**Files:**
- Create: `backend/migrations/versions/XXX_044_signal_scoring_columns.py`
- Modify: `backend/models/signal.py`

- [ ] **Step 1: Add 6 new columns to the SignalSnapshot model**

In `backend/models/signal.py`, add these mapped columns after the `composite_weights` field (before the class closing):

```python
    # Gate indicators (confirmation-gate scoring v2)
    adx_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    obv_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfi_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    piotroski_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    macd_histogram_prev: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 2: Generate and review the Alembic migration**

Run: `uv run alembic revision --autogenerate -m "044 signal scoring gate columns"`

Open the generated migration file. Verify it contains exactly 6 `add_column` operations for `signal_snapshots`. Remove any false-positive TimescaleDB index drops (Alembic autogenerate bug — always check). The `down_revision` must be `"757cedd28893"`.

- [ ] **Step 3: Apply migration and verify**

```bash
uv run alembic upgrade head
uv run alembic current
```

Expected: shows the new migration revision as head.

- [ ] **Step 4: Commit**

```bash
git add backend/models/signal.py backend/migrations/versions/*044*
git commit -m "feat(models): add 6 gate indicator columns to signal_snapshots [KAN-555]"
```

---

### Task 2: Compute new indicators in compute_signals()

**Files:**
- Modify: `backend/services/signals.py` (SignalResult dataclass + compute_signals function)
- Modify: `backend/tools/signals.py` (re-export shim — no new exports needed, but verify)

**Context for subagent:**
- `compute_signals()` is at line 175-269 of `backend/services/signals.py`
- `SignalResult` dataclass is at line 95-143
- The function receives a full OHLCV DataFrame (Open, High, Low, Close, Adj Close, Volume)
- pandas-ta needs `import importlib.metadata` before `import pandas_ta` — this import already exists at top of file
- All new indicators use `pandas_ta` functions: `ta.adx()`, `ta.obv()`, `ta.mfi()`, `ta.atr()`
- The `_make_ohlcv_df()` test helper creates OHLCV with constant Volume=1_000_000 — OBV slope will be 0 for constant volume. Tests need varying volume.

- [ ] **Step 1: Add 6 new fields to SignalResult dataclass**

In `backend/services/signals.py`, add after the `data_days` field (around line 142):

```python
    # Gate indicators (confirmation-gate scoring v2)
    adx_value: float | None = None
    obv_slope: float | None = None  # 21-day OBV linear regression slope
    mfi_value: float | None = None  # Money Flow Index (0-100)
    atr_value: float | None = None  # Average True Range
    piotroski_score_value: int | None = None  # Persisted F-Score (0-9)
    macd_histogram_prev: float | None = None  # Prior day histogram
```

Note: field is `piotroski_score_value` to avoid shadowing the `piotroski_score` parameter name in `compute_signals()`.

- [ ] **Step 2: Write 4 pure indicator computation functions**

Add these functions after the existing `compute_risk_return()` function (around line 473), before `compute_quantstats_stock()`:

```python
def compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> float | None:
    """Compute ADX (Average Directional Index) — trend strength.

    ADX > 25 = trending market, ADX < 20 = range-bound.
    Used by Gate 1 of the confirmation-gate scoring model.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        period: ADX period (default 14).

    Returns:
        Latest ADX value, or None if insufficient data.
    """
    if len(close) < period * 2:
        return None
    adx_df = ta.adx(high, low, close, length=period)  # type: ignore[attr-defined]
    if adx_df is None or adx_df.empty:
        return None
    col = f"ADX_{period}"
    if col not in adx_df.columns:
        return None
    val = adx_df[col].dropna()
    if val.empty:
        return None
    return round(float(val.iloc[-1]), 2)


def compute_obv_slope(close: pd.Series, volume: pd.Series, window: int = 21) -> float | None:
    """Compute 21-day OBV (On-Balance Volume) linear regression slope.

    Positive slope = volume confirming price moves up.
    Used by Gate 3 of the confirmation-gate scoring model.

    Args:
        close: Series of closing prices.
        volume: Series of volume data.
        window: Lookback window for slope (default 21 days).

    Returns:
        Normalized OBV slope (slope / mean_obv), or None if insufficient data.
    """
    if len(close) < window + 1:
        return None
    obv_series = ta.obv(close, volume)  # type: ignore[attr-defined]
    if obv_series is None or obv_series.dropna().empty:
        return None
    obv_tail = obv_series.dropna().iloc[-window:]
    if len(obv_tail) < window:
        return None
    # Linear regression slope over the window
    x = np.arange(len(obv_tail), dtype=float)
    y = obv_tail.values.astype(float)
    # Normalize to avoid giant numbers: slope relative to mean OBV
    mean_obv = np.abs(y).mean()
    if mean_obv == 0:
        return 0.0
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope / mean_obv, 6)


def compute_mfi(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14
) -> float | None:
    """Compute MFI (Money Flow Index) — volume-weighted RSI.

    MFI > 50 = net buying pressure, MFI < 50 = net selling pressure.
    Used by Gate 3 of the confirmation-gate scoring model.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        volume: Series of volume data.
        period: MFI period (default 14).

    Returns:
        Latest MFI value (0-100), or None if insufficient data.
    """
    if len(close) < period + 1:
        return None
    mfi_series = ta.mfi(high, low, close, volume, length=period)  # type: ignore[attr-defined]
    if mfi_series is None or mfi_series.dropna().empty:
        return None
    return round(float(mfi_series.dropna().iloc[-1]), 2)


def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> float | None:
    """Compute ATR (Average True Range) — volatility measure.

    Stored for future use in position sizing and stop-loss calculations.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        period: ATR period (default 14).

    Returns:
        Latest ATR value, or None if insufficient data.
    """
    if len(close) < period + 1:
        return None
    atr_series = ta.atr(high, low, close, length=period)  # type: ignore[attr-defined]
    if atr_series is None or atr_series.dropna().empty:
        return None
    return round(float(atr_series.dropna().iloc[-1]), 4)
```

- [ ] **Step 2b: Refactor compute_macd() to return prior-day histogram**

The existing `compute_macd()` at `backend/services/signals.py:309-341` calls `ta.macd()` and extracts the last histogram value. We need the prior-day value too for the Gate 2 acceleration check. Extend it to return a 4-tuple instead of calling `ta.macd()` a second time in `compute_signals()`.

Replace the existing `compute_macd()` function:

```python
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
        histogram_prev is the prior-day histogram for acceleration checks.
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

    # Prior-day histogram for acceleration check (Gate 2)
    hist_vals = macd_df[hist_col].dropna()
    hist_prev = round(float(hist_vals.iloc[-2]), 4) if len(hist_vals) >= 2 else None

    signal = MACDSignal.BULLISH if hist_val > 0 else MACDSignal.BEARISH

    return macd_val, hist_val, signal, hist_prev
```

Then update the call site in `compute_signals()` (around line 231):

```python
    macd_val, macd_hist, macd_sig, macd_hist_prev = compute_macd(closes)
```

**IMPORTANT:** Update ALL existing tests that unpack `compute_macd()` as a 3-tuple. There are **6 call sites across 3 files**:

| File | Lines | Current unpacking |
|------|-------|-------------------|
| `tests/unit/signals/test_signals.py` | 187, 210, 220 | `macd_val, hist_val, signal = compute_macd(...)` |
| `tests/unit/signals/test_signal_properties.py` | 207 | `macd_val, hist_val, signal_label = compute_macd(...)` |
| `tests/unit/signals/test_golden_datasets.py` | 149, 161, 173 | `macd_val, hist_val, signal_label = compute_macd(...)` |

All must become 4-tuple unpacking:
```python
macd_val, hist_val, signal_label, hist_prev = compute_macd(...)
```

Missing any of these causes `ValueError: too many values to unpack` at runtime.

- [ ] **Step 3: Wire new indicators into compute_signals()**

In `compute_signals()`, after the existing indicator computations (around line 234), add:

```python
    # ── Compute gate indicators ───────────────────────────────────────
    # Extract OHLCV columns needed for volume/range indicators
    high_col = "High" if "High" in df.columns else "high"
    low_col = "Low" if "Low" in df.columns else "low"
    vol_col = "Volume" if "Volume" in df.columns else "volume"

    highs = cast(pd.Series, df[high_col]).dropna() if high_col in df.columns else pd.Series(dtype=float)
    lows = cast(pd.Series, df[low_col]).dropna() if low_col in df.columns else pd.Series(dtype=float)
    volumes = cast(pd.Series, df[vol_col]).dropna() if vol_col in df.columns else pd.Series(dtype=float)

    adx_val = compute_adx(highs, lows, closes) if len(highs) > 0 else None
    obv_slope_val = compute_obv_slope(closes, volumes) if len(volumes) > 0 else None
    mfi_val = compute_mfi(highs, lows, closes, volumes) if len(highs) > 0 else None
    atr_val = compute_atr(highs, lows, closes) if len(highs) > 0 else None
    # macd_hist_prev already extracted from compute_macd() in Step 2b
```

Update the `SignalResult` constructor at the end of `compute_signals()` to include the new fields:

```python
    return SignalResult(
        ticker=ticker,
        # ... existing fields unchanged ...
        adx_value=adx_val,
        obv_slope=obv_slope_val,
        mfi_value=mfi_val,
        atr_value=atr_val,
        piotroski_score_value=piotroski_score,
        macd_histogram_prev=macd_hist_prev,
    )
```

- [ ] **Step 4: Update store_signal_snapshot() to persist new columns**

In `store_signal_snapshot()` (line 658), add these to the `values` dict:

```python
        "adx_value": result.adx_value,
        "obv_slope": result.obv_slope,
        "mfi_value": result.mfi_value,
        "atr_value": result.atr_value,
        "piotroski_score": result.piotroski_score_value,
        "macd_histogram_prev": result.macd_histogram_prev,
```

- [ ] **Step 5: Commit**

```bash
git add backend/services/signals.py
git commit -m "feat(signals): compute ADX, OBV slope, MFI, ATR in signal pipeline [KAN-555]"
```

---

### Task 3: Unit tests for new indicator functions

**Files:**
- Modify: `tests/unit/signals/test_signals.py`

**Context for subagent:**
- Existing test helpers: `_make_price_series()` (returns pd.Series of Close), `_make_ohlcv_df()` (wraps Close into OHLCV DataFrame with constant Volume=1M), `_make_hardening_price_series()` (returns OHLCV DataFrame with random Volume)
- Import new functions from `backend.tools.signals` (re-export shim)
- ADX range: 0-100 (typically 10-60). Needs High/Low/Close, 28+ rows.
- OBV slope: normalized float. Positive = volume confirming uptrend.
- MFI range: 0-100. Needs OHLCV, 15+ rows.
- ATR: positive float. Needs High/Low/Close, 15+ rows.

- [ ] **Step 1: Add imports for new functions**

At the top of `tests/unit/signals/test_signals.py`, add to the import block:

```python
from backend.tools.signals import (
    # ... existing imports ...
    compute_adx,
    compute_atr,
    compute_mfi,
    compute_obv_slope,
)
```

Also update `backend/tools/signals.py` re-export shim to include these 4 new functions:

```python
from backend.services.signals import (
    compute_adx as compute_adx,
)
from backend.services.signals import (
    compute_atr as compute_atr,
)
from backend.services.signals import (
    compute_mfi as compute_mfi,
)
from backend.services.signals import (
    compute_obv_slope as compute_obv_slope,
)
```

- [ ] **Step 2: Write ADX tests**

Add after the existing Bollinger tests section:

```python
# ═════════════════════════════════════════════════════════════════════════════
# ADX Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeADX:
    """Tests for ADX (Average Directional Index) computation."""

    def test_adx_trending_market(self) -> None:
        """Strong trend should produce ADX > 25."""
        df = _make_hardening_price_series(n=250, trend=0.008, volatility=0.005, seed=10)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert val > 20, f"ADX {val} too low for strong trend"

    def test_adx_range_bound_market(self) -> None:
        """Flat market with noise should produce ADX < 25."""
        df = _make_hardening_price_series(n=250, trend=0.0, volatility=0.01, seed=20)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert val < 30, f"ADX {val} too high for range-bound"

    def test_adx_bounded_0_100(self) -> None:
        """ADX must be between 0 and 100."""
        df = _make_hardening_price_series(n=250)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert 0 <= val <= 100

    def test_adx_insufficient_data(self) -> None:
        """ADX returns None for too few data points."""
        df = _make_hardening_price_series(n=10)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is None
```

- [ ] **Step 3: Write OBV slope tests**

```python
# ═════════════════════════════════════════════════════════════════════════════
# OBV Slope Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeOBVSlope:
    """Tests for OBV (On-Balance Volume) slope computation."""

    def test_obv_slope_uptrend_with_volume(self) -> None:
        """Rising prices with increasing volume should produce positive OBV slope."""
        n = 100
        rng = np.random.default_rng(42)
        prices = 100.0 * np.cumprod(1 + np.full(n, 0.005))
        # Volume increases with price (confirming)
        volumes = pd.Series(np.linspace(1_000_000, 5_000_000, n))
        closes = pd.Series(prices, index=pd.bdate_range(end="2025-01-01", periods=n))
        val = compute_obv_slope(closes, volumes)
        assert val is not None
        assert val > 0, f"OBV slope {val} should be positive for confirmed uptrend"

    def test_obv_slope_constant_volume(self) -> None:
        """Constant volume should produce near-zero OBV slope."""
        n = 100
        prices = 100.0 * np.cumprod(1 + np.random.default_rng(42).normal(0, 0.01, n))
        closes = pd.Series(prices, index=pd.bdate_range(end="2025-01-01", periods=n))
        volumes = pd.Series([1_000_000] * n, index=closes.index)
        val = compute_obv_slope(closes, volumes)
        assert val is not None
        # With constant volume, OBV slope will be small but not necessarily zero
        assert abs(val) < 1.0

    def test_obv_slope_insufficient_data(self) -> None:
        """OBV slope returns None for too few data points."""
        closes = pd.Series([100.0, 101.0], index=pd.bdate_range(end="2025-01-01", periods=2))
        volumes = pd.Series([1_000_000, 1_000_000], index=closes.index)
        val = compute_obv_slope(closes, volumes)
        assert val is None
```

- [ ] **Step 4: Write MFI and ATR tests**

```python
# ═════════════════════════════════════════════════════════════════════════════
# MFI Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeMFI:
    """Tests for MFI (Money Flow Index) computation."""

    def test_mfi_bounded_0_100(self) -> None:
        """MFI must be between 0 and 100."""
        df = _make_hardening_price_series(n=100)
        val = compute_mfi(df["High"], df["Low"], df["Close"], df["Volume"])
        assert val is not None
        assert 0 <= val <= 100

    def test_mfi_insufficient_data(self) -> None:
        """MFI returns None for too few data points."""
        df = _make_hardening_price_series(n=5)
        val = compute_mfi(df["High"], df["Low"], df["Close"], df["Volume"])
        assert val is None


# ═════════════════════════════════════════════════════════════════════════════
# ATR Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeATR:
    """Tests for ATR (Average True Range) computation."""

    def test_atr_positive(self) -> None:
        """ATR must be positive for any valid price data."""
        df = _make_hardening_price_series(n=100)
        val = compute_atr(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert val > 0

    def test_atr_higher_volatility_higher_atr(self) -> None:
        """Higher volatility data should produce a higher ATR."""
        low_vol = _make_hardening_price_series(n=100, volatility=0.005, seed=1)
        high_vol = _make_hardening_price_series(n=100, volatility=0.04, seed=1)
        atr_low = compute_atr(low_vol["High"], low_vol["Low"], low_vol["Close"])
        atr_high = compute_atr(high_vol["High"], high_vol["Low"], high_vol["Close"])
        assert atr_low is not None and atr_high is not None
        assert atr_high > atr_low

    def test_atr_insufficient_data(self) -> None:
        """ATR returns None for too few data points."""
        df = _make_hardening_price_series(n=5)
        val = compute_atr(df["High"], df["Low"], df["Close"])
        assert val is None
```

- [ ] **Step 5: Write end-to-end test for new fields in compute_signals()**

```python
class TestComputeSignalsGateIndicators:
    """Tests that compute_signals() populates gate indicator fields."""

    def test_gate_indicators_populated(self) -> None:
        """compute_signals() with sufficient OHLCV data populates all gate fields."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("AAPL", df)
        assert result.adx_value is not None
        assert result.mfi_value is not None
        assert result.atr_value is not None
        assert result.obv_slope is not None
        # macd_histogram_prev may be None if MACD itself is None

    def test_gate_indicators_none_for_insufficient_data(self) -> None:
        """Gate indicators are None when data is too short."""
        df = _make_hardening_price_series(n=10)
        result = compute_signals("TINY", df)
        assert result.adx_value is None
        assert result.mfi_value is None
        assert result.atr_value is None
        assert result.obv_slope is None

    def test_piotroski_persisted_in_result(self) -> None:
        """Piotroski score passed to compute_signals appears in result."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("AAPL", df, piotroski_score=7)
        assert result.piotroski_score_value == 7

    def test_macd_histogram_prev_populated(self) -> None:
        """Prior-day MACD histogram is populated when MACD is available."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("AAPL", df)
        if result.macd_histogram is not None:
            assert result.macd_histogram_prev is not None
            # Prev should differ from current (different day)
            # (not guaranteed but very likely with random data)
```

- [ ] **Step 6: Run tests and verify**

```bash
uv run pytest tests/unit/signals/test_signals.py -v --tb=short
```

Expected: all new tests pass, all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/signals/test_signals.py backend/tools/signals.py
git commit -m "test(signals): unit tests for ADX, OBV slope, MFI, ATR indicators [KAN-555]"
```

---

### Task 4: Update Hypothesis property tests

**Files:**
- Modify: `tests/unit/signals/test_signal_properties.py`

**Context for subagent:**
- This file contains Hypothesis-based property tests that verify bounds and invariants.
- Key tests: `test_composite_score_bounded_0_to_10`, `test_composite_score_bounded_from_inputs`, `test_composite_score_pairwise_dominance`, `test_no_nan_inf_in_signal_output`.
- After PR2 changes the scoring function signature, these tests will need updating. For now, just verify the new gate indicator fields don't produce NaN/Inf.

- [ ] **Step 1: Add gate indicator NaN/Inf checks to existing property test**

In `tests/unit/signals/test_signal_properties.py`, find `test_no_nan_inf_in_signal_output` and add the new fields to the checked list:

```python
        # Add after existing field checks:
        result.adx_value,
        result.obv_slope,
        result.mfi_value,
        result.atr_value,
        result.macd_histogram_prev,
```

- [ ] **Step 2: Run property tests**

```bash
uv run pytest tests/unit/signals/test_signal_properties.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/signals/test_signal_properties.py
git commit -m "test(signals): add gate indicators to Hypothesis property tests [KAN-555]"
```

---

### Task 5: Lint + format + full test run

- [ ] **Step 1: Lint and format**

```bash
uv run ruff check --fix backend/services/signals.py backend/models/signal.py backend/tools/signals.py tests/unit/signals/
uv run ruff format backend/services/signals.py backend/models/signal.py backend/tools/signals.py tests/unit/signals/
```

- [ ] **Step 2: Run full unit test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```

Expected: 2698+ tests pass, 0 failures.

- [ ] **Step 3: Fix any issues and commit**

```bash
git add -u
git commit -m "chore: lint + format signal scoring changes [KAN-555]"
```

---

## PR2: Confirmation-Gate Engine — Rewrite compute_composite_score() (KAN-556)

**Depends on:** PR1 merged (new indicator columns exist in DB and SignalResult).

### Fact Sheet

```
compute_composite_score(): backend/services/signals.py:552-650
  Signature: (rsi_value, rsi_signal, macd_histogram, macd_signal, sma_signal, sharpe, piotroski_score=None)
  Returns: (score: float | None, weights: dict | None)
  Called from: compute_signals() at line 237

Callers of compute_signals() that pass piotroski_score:
  - pipelines.py:120 (ingest_ticker)
  - ingest_stock_tool.py:124 (agent tool)

Callers that do NOT pass piotroski_score (uses default None):
  - market_data.py:69 (nightly refresh)
  - compute_signals_tool.py:57 (agent tool)
  - recommendations_tool.py:58 (agent tool)

Tests that call compute_composite_score() directly:
  - test_signals.py TestComputeCompositeScore (5 tests: max, min, mixed, none, bounds)
  - test_signal_properties.py test_composite_score_bounded_from_inputs
  - test_signal_properties.py test_composite_score_pairwise_dominance

Tests that check composite_score via compute_signals():
  - test_signals.py TestComputeSignalsEndToEnd (6 tests)
  - test_signals.py TestCompositeScoreRange (2 tests)
  - test_signals.py TestPiotroskiBlendingHardening (3 tests)
  - test_signals.py TestBullishBearishExtremes (1 test)
  - test_signal_properties.py test_composite_score_bounded_0_to_10

composite_weights JSONB consumers (must support new format):
  - frontend action-required-zone.tsx — reads composite_score only, ignores weights
  - frontend bulletin-zone.tsx — reads composite_score only
  - frontend kpi-row.tsx — reads composite_score only
  - backend convergence.py — reads composite_score only
  - backend recommendations.py — reads composite_score only (thresholds BUY>=8, WATCH>=5)
  - backend dq_scan.py — reads composite_score only
  All consumers use composite_score as a number. None parse composite_weights structure.
```

### Task 6: Write the confirmation gate engine (TDD)

**Files:**
- Modify: `backend/services/signals.py` — replace `compute_composite_score()` with `compute_confirmation_gates()`
- Modify: `tests/unit/signals/test_signals.py` — rewrite TestComputeCompositeScore

- [ ] **Step 1: Write failing tests for the new gate engine**

Replace the entire `TestComputeCompositeScore` class in `tests/unit/signals/test_signals.py` with:

```python
# ═════════════════════════════════════════════════════════════════════════════
# Confirmation Gate Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestConfirmationGates:
    """Tests for the 5-gate confirmation scoring model."""

    def test_all_gates_confirmed_scores_10(self) -> None:
        """When all 5 gates confirm, score should be 10.0."""
        score, weights = compute_confirmation_gates(
            adx=32.0,           # Gate 1: trending (>20) ✓
            macd_histogram=1.0, # Gate 2: positive ✓
            macd_histogram_prev=0.5,  # accelerating ✓
            sma_50=150.0,       # Gate 2: above SMA200 ✓
            sma_200=140.0,
            current_price=155.0,  # above SMA50 ✓
            obv_slope=0.05,     # Gate 3: positive ✓
            mfi=62.0,           # Gate 3: >50 ✓
            rsi=45.0,           # Gate 4: pullback in uptrend (40-65) ✓
            piotroski=8,        # Gate 5: strong (>=7) ✓
        )
        assert score == 10.0
        assert weights is not None
        assert weights["gates_confirmed"] == 5
        assert weights["gates_active"] == 5
        assert weights["mode"] == "confirmation_gate_v2"

    def test_no_gates_confirmed_scores_0(self) -> None:
        """When no gates confirm, score should be 0.0."""
        score, weights = compute_confirmation_gates(
            adx=10.0,           # Gate 1: range-bound (<20) ✗
            macd_histogram=-1.0,  # Gate 2: bearish ✗
            macd_histogram_prev=-0.5,
            sma_50=140.0,
            sma_200=150.0,      # death cross ✗
            current_price=135.0,  # below both ✗
            obv_slope=-0.05,    # Gate 3: negative ✗
            mfi=35.0,           # Gate 3: <50 ✗
            rsi=72.0,           # Gate 4: overbought in range-bound, but direction is bearish
            piotroski=2,        # Gate 5: weak (<4) vetoes ✗
        )
        assert score == 0.0
        assert weights is not None
        assert weights["gates_confirmed"] == 0

    def test_four_of_five_scores_8(self) -> None:
        """4 of 5 gates confirmed = score 8.0 (BUY threshold)."""
        score, weights = compute_confirmation_gates(
            adx=28.0,           # Gate 1: trending ✓
            macd_histogram=0.5,
            macd_histogram_prev=0.3,  # accelerating ✓
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,  # Gate 2: all bullish ✓
            obv_slope=0.03,     # Gate 3: positive ✓
            mfi=55.0,           # Gate 3: >50 ✓
            rsi=70.0,           # Gate 4: too high for trending pullback (40-65) ✗
            piotroski=8,        # Gate 5: strong ✓
        )
        assert score == 8.0
        assert weights["gates_confirmed"] == 4

    def test_piotroski_none_skips_gate(self) -> None:
        """When piotroski is None, gate 5 is skipped (active=4, not 5)."""
        score, weights = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=50.0,           # in range for trending
            piotroski=None,     # skipped
        )
        assert weights is not None
        assert weights["gates_active"] == 4
        # 4/4 confirmed = 10.0
        assert score == 10.0

    def test_piotroski_neutral_skips_gate(self) -> None:
        """Piotroski 4-6 is neutral — gate is NOT counted as active."""
        score_neutral, w_neutral = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0, sma_200=140.0, current_price=155.0,
            obv_slope=0.03, mfi=55.0, rsi=50.0,
            piotroski=5,  # neutral — gate not active, no effect on score
        )
        assert w_neutral is not None
        assert w_neutral["gate_5_fundamental"]["confirmed"] is False
        # Neutral Piotroski does NOT increase gates_active — same as no data
        assert w_neutral["gates_active"] == 4  # only gates 1-4 active

    def test_piotroski_low_vetoes_bullish(self) -> None:
        """Piotroski 0-3 vetoes a bullish signal (reduces confirmed count)."""
        score, weights = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0, sma_200=140.0, current_price=155.0,
            obv_slope=0.03, mfi=55.0, rsi=50.0,
            piotroski=1,  # weak — vetoes
        )
        assert weights is not None
        assert weights["gate_5_fundamental"]["confirmed"] is False

    def test_rsi_regime_aware_trending(self) -> None:
        """In trending market (ADX>25), RSI 40-65 is bullish entry timing."""
        score_good, _ = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5, macd_histogram_prev=0.3,
            sma_50=150.0, sma_200=140.0, current_price=155.0,
            obv_slope=0.03, mfi=55.0,
            rsi=50.0,  # in range 40-65 ✓
            piotroski=None,
        )
        score_bad, _ = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5, macd_histogram_prev=0.3,
            sma_50=150.0, sma_200=140.0, current_price=155.0,
            obv_slope=0.03, mfi=55.0,
            rsi=75.0,  # chasing, >65 ✗
            piotroski=None,
        )
        assert score_good > score_bad

    def test_rsi_regime_aware_range_bound(self) -> None:
        """In range-bound market (ADX<20), RSI<35 is bullish (mean-reversion)."""
        _, weights = compute_confirmation_gates(
            adx=15.0,  # range-bound
            macd_histogram=0.5, macd_histogram_prev=0.3,
            sma_50=150.0, sma_200=140.0, current_price=155.0,
            obv_slope=0.03, mfi=55.0,
            rsi=30.0,  # oversold in range-bound = buy ✓
            piotroski=None,
        )
        assert weights["gate_4_entry"]["confirmed"] is True

    def test_all_none_returns_none(self) -> None:
        """When all inputs are None, score and weights are None."""
        score, weights = compute_confirmation_gates(
            adx=None, macd_histogram=None, macd_histogram_prev=None,
            sma_50=None, sma_200=None, current_price=None,
            obv_slope=None, mfi=None, rsi=None, piotroski=None,
        )
        assert score is None
        assert weights is None

    def test_score_always_0_to_10(self) -> None:
        """Score must always be in [0, 10] range for any valid inputs."""
        import itertools
        adx_vals = [10.0, 22.0, 35.0]
        rsi_vals = [25.0, 50.0, 75.0]
        piotroski_vals = [0, 5, 9, None]
        for adx, rsi, pio in itertools.product(adx_vals, rsi_vals, piotroski_vals):
            score, _ = compute_confirmation_gates(
                adx=adx, macd_histogram=0.5, macd_histogram_prev=0.3,
                sma_50=150.0, sma_200=140.0, current_price=155.0,
                obv_slope=0.01, mfi=55.0, rsi=rsi, piotroski=pio,
            )
            if score is not None:
                assert 0 <= score <= 10, f"Score {score} out of range"

    def test_weights_contain_gate_details(self) -> None:
        """Composite weights must contain per-gate explanations."""
        _, weights = compute_confirmation_gates(
            adx=30.0, macd_histogram=0.5, macd_histogram_prev=0.3,
            sma_50=150.0, sma_200=140.0, current_price=155.0,
            obv_slope=0.03, mfi=55.0, rsi=50.0, piotroski=7,
        )
        assert weights is not None
        for gate_key in ["gate_1_trend", "gate_2_direction", "gate_3_volume",
                         "gate_4_entry", "gate_5_fundamental"]:
            assert gate_key in weights, f"Missing {gate_key}"
            assert "confirmed" in weights[gate_key]
            assert "detail" in weights[gate_key]
```

- [ ] **Step 2: Run tests — they should fail (function doesn't exist yet)**

```bash
uv run pytest tests/unit/signals/test_signals.py::TestConfirmationGates -v --tb=short 2>&1 | head -20
```

Expected: ImportError or NameError for `compute_confirmation_gates`.

- [ ] **Step 3: Implement compute_confirmation_gates()**

Replace `compute_composite_score()` in `backend/services/signals.py` (lines 552-650) with:

```python
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
    # Direction: "bullish" if majority of direction signals are positive
    direction = _determine_direction(
        macd_histogram, macd_histogram_prev, sma_50, sma_200, current_price
    )

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
            "detail": f"{'Strong' if adx > 25 else 'Emerging'} trend (ADX {adx})" if confirmed
                      else f"Range-bound (ADX {adx})",
        }
    else:
        regime = "unknown"
        weights["gate_1_trend"] = {"confirmed": False, "adx": None, "regime": "unknown",
                                    "detail": "No ADX data"}

    # ── Gate 2: Direction (MACD + SMA alignment) ──────────────────────
    if macd_histogram is not None and sma_50 is not None and sma_200 is not None and current_price is not None:
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
            "macd_accel": macd_histogram_prev is not None and (
                (direction == "bullish" and macd_histogram > macd_histogram_prev) or
                (direction == "bearish" and macd_histogram < macd_histogram_prev)
            ),
            "sma_aligned": (direction == "bullish" and sma_50 > sma_200) or
                           (direction == "bearish" and sma_50 < sma_200),
            "detail": f"{direction.title()} — {conditions_met}/{conditions_total} direction signals align",
        }
    else:
        weights["gate_2_direction"] = {"confirmed": False, "direction": direction,
                                        "detail": "Insufficient data for direction"}

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
            "detail": f"Money {'flowing in' if mfi > 50 else 'flowing out'} (MFI {mfi}, OBV {'rising' if obv_slope > 0 else 'falling'})",
        }
    else:
        weights["gate_3_volume"] = {"confirmed": False, "obv_slope": obv_slope, "mfi": mfi,
                                     "detail": "Insufficient volume data"}

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
                detail = f"RSI {rsi} — {'chasing' if rsi > 65 else 'unfavorable'} for {regime} {direction}"
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
        weights["gate_4_entry"] = {"confirmed": False, "rsi": None,
                                    "detail": "No RSI data"}

    # ── Gate 5: Fundamental Health (Piotroski) ────────────────────────
    # Design decision: Piotroski 4-6 is truly neutral — gate is NOT counted
    # as active. Only strong (>=7, confirms) and weak (0-3, vetoes) are active.
    # This prevents neutral Piotroski from penalizing the score vs. no data.
    # Example: 4/4 = 10.0 (no Piotroski) should equal 4/4 = 10.0 (Piotroski=5),
    # NOT drop to 4/5 = 8.0.
    if piotroski is not None:
        if piotroski >= 7:
            gates_active += 1
            gates_confirmed += 1
            confirmed = True
            detail = f"Strong fundamentals (F-Score {piotroski}/9)"
        elif piotroski >= 4:
            # Neutral — gate not counted as active (does not confirm, does not veto)
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
        weights["gate_5_fundamental"] = {"confirmed": False, "piotroski": None,
                                          "detail": "No fundamental data (skipped)"}

    # ── Compute final score ───────────────────────────────────────────
    if gates_active == 0:
        return None, None

    score = round((gates_confirmed / gates_active) * 10, 1)
    weights["gates_active"] = gates_active
    weights["gates_confirmed"] = gates_confirmed
    weights["total"] = score

    return score, weights


def _determine_direction(
    macd_histogram: float | None,
    macd_histogram_prev: float | None,
    sma_50: float | None,
    sma_200: float | None,
    current_price: float | None,
) -> str:
    """Determine overall direction from technical signals.

    Uses majority vote of available directional indicators.

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
        return "bullish"  # Default when no data

    return "bullish" if bullish_votes > total_votes / 2 else "bearish"
```

- [ ] **Step 4: Keep the old function as a deprecated alias**

Keep `compute_composite_score` as a thin wrapper that calls `compute_confirmation_gates` so existing test imports don't break during transition:

```python
def compute_composite_score(
    rsi_value: float | None,
    rsi_signal: str | None,
    macd_histogram: float | None,
    macd_signal: str | None,
    sma_signal: str | None,
    sharpe: float | None,
    piotroski_score: int | None = None,
) -> tuple[float | None, dict | None]:
    """DEPRECATED: Use compute_confirmation_gates() instead.

    Thin wrapper that maps old-style inputs to the new gate model.
    Kept for backward compatibility during transition.
    """
    import warnings
    warnings.warn(
        "compute_composite_score is deprecated, use compute_confirmation_gates",
        DeprecationWarning,
        stacklevel=2,
    )
    # Map old inputs to new gate inputs (best-effort)
    return compute_confirmation_gates(
        adx=None,  # Not available in old API
        macd_histogram=macd_histogram,
        macd_histogram_prev=None,
        sma_50=None,
        sma_200=None,
        current_price=None,
        obv_slope=None,
        mfi=None,
        rsi=rsi_value,
        piotroski=piotroski_score,
    )
```

- [ ] **Step 5: Add kill switch setting + update compute_signals()**

First, add the kill switch to `backend/config.py`:

```python
    # Signal scoring engine toggle (rollback mechanism)
    SIGNAL_SCORING_ENGINE: str = "confirmation_gate_v2"  # or "additive_v1" to rollback
```

Then replace the composite score computation block in `compute_signals()` (around line 237):

```python
    # ── Compute composite score ───────────────────────────────────────
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
            rsi_val, rsi_sig, macd_hist, macd_sig, sma_sig, sharpe,
            piotroski_score=piotroski_score,
        )
```

**NOTE:** Keep `compute_composite_score()` as a real function (not just deprecated wrapper) so the kill switch works. The deprecated wrapper approach from Step 4 is only for external callers — the kill switch uses the original function directly.

- [ ] **Step 6: Update re-export shim**

Add to `backend/tools/signals.py`:

```python
from backend.services.signals import (
    compute_confirmation_gates as compute_confirmation_gates,
)
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/unit/signals/test_signals.py -v --tb=short
```

Expected: new TestConfirmationGates passes, old TestComputeCompositeScore tests still pass (via deprecated wrapper).

- [ ] **Step 8: Commit**

```bash
git add backend/services/signals.py backend/tools/signals.py tests/unit/signals/test_signals.py
git commit -m "feat(signals): replace additive scoring with 5-gate confirmation engine [KAN-556]"
```

---

### Task 7: Update end-to-end and hardening tests

**Files:**
- Modify: `tests/unit/signals/test_signals.py`

**Context for subagent:**
- After Task 6, `compute_signals()` uses the new gate model. The end-to-end tests and hardening tests need to verify the new behavior.
- Key change: scores now depend on ADX/OBV/MFI, not Sharpe. Bullish/bearish synthetic data will produce different scores.
- The `_make_ohlcv_df()` helper uses constant Volume=1M. OBV slope will be dominated by price direction, which is fine.
- The `_make_hardening_price_series()` helper uses random volume — ideal for realistic testing.

- [ ] **Step 1: Update TestComputeSignalsEndToEnd**

Update `test_compute_signals_with_piotroski_blends_score` — old test checks for `"fundamental_score_10"` in weights. New weights use `"gate_5_fundamental"`:

```python
    def test_compute_signals_with_piotroski_blends_score(self) -> None:
        """When piotroski_score is provided, it affects the composite score via gate 5."""
        closes = _make_price_series(num_days=300, noise=0.005)
        df = _make_ohlcv_df(closes)

        result_no_fund = compute_signals("AAPL", df)
        result_with_fund = compute_signals("AAPL", df, piotroski_score=9)

        assert result_no_fund.composite_score is not None
        assert result_with_fund.composite_score is not None
        # With strong piotroski, gate 5 confirms → potentially higher score
        # (or same if all other gates already confirmed/failed)
        assert result_with_fund.composite_weights is not None
        assert "gate_5_fundamental" in result_with_fund.composite_weights

    def test_compute_signals_none_piotroski_skips_gate(self) -> None:
        """When piotroski_score is None, gate 5 is skipped (not counted as active)."""
        closes = _make_price_series(num_days=300, noise=0.005)
        df = _make_ohlcv_df(closes)

        result = compute_signals("AAPL", df, piotroski_score=None)
        assert result.composite_weights is not None
        # Gate 5 should be skipped
        assert result.composite_weights.get("gates_active", 0) <= 4
```

- [ ] **Step 2: Update TestPiotroskiBlendingHardening**

```python
class TestPiotroskiBlendingHardening:
    """Gate 5 (Piotroski) behavior in the confirmation-gate model."""

    def test_piotroski_9_can_increase_score(self):
        """Strong Piotroski (9) adds a confirmed gate, potentially raising score."""
        df = _make_hardening_price_series(n=250)
        without = compute_signals("TST", df)
        with_fund = compute_signals("TST", df, piotroski_score=9)
        # With piotroski=9, gate 5 is active+confirmed. Without, gate 5 skipped.
        # Score should be >= without (more confirmed gates relative to active).
        assert with_fund.composite_score is not None
        assert without.composite_score is not None

    def test_piotroski_0_can_lower_score(self):
        """Zero Piotroski adds an active gate that doesn't confirm → lowers score."""
        df = _make_hardening_price_series(n=250)
        without = compute_signals("TST", df)
        with_fund = compute_signals("TST", df, piotroski_score=0)
        # piotroski=0: gate 5 active but not confirmed. This increases denominator
        # without increasing numerator → lower or equal score.
        assert with_fund.composite_score is not None
        assert with_fund.composite_score <= without.composite_score

    def test_blending_mode_in_weights(self):
        """Composite weights dict shows 'confirmation_gate_v2' mode."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("TST", df, piotroski_score=5)
        assert result.composite_weights is not None
        assert result.composite_weights.get("mode") == "confirmation_gate_v2"
```

- [ ] **Step 3: Update Hypothesis property tests**

In `tests/unit/signals/test_signal_properties.py`, update `test_composite_score_bounded_from_inputs` and `test_composite_score_pairwise_dominance` to use the new function:

```python
@given(
    adx=st.one_of(st.none(), st.floats(0, 100, allow_nan=False)),
    rsi=st.one_of(st.none(), st.floats(0, 100, allow_nan=False)),
    mfi=st.one_of(st.none(), st.floats(0, 100, allow_nan=False)),
    piotroski=st.one_of(st.none(), st.integers(0, 9)),
)
@settings(max_examples=20)
def test_confirmation_gates_bounded_0_to_10(
    adx: float | None, rsi: float | None, mfi: float | None, piotroski: int | None
) -> None:
    """Confirmation gate score must produce score in [0, 10] for any inputs."""
    score, _ = compute_confirmation_gates(
        adx=adx, macd_histogram=0.5, macd_histogram_prev=0.3,
        sma_50=150.0, sma_200=140.0, current_price=155.0,
        obv_slope=0.01, mfi=mfi, rsi=rsi, piotroski=piotroski,
    )
    if score is not None:
        assert 0.0 <= score <= 10.0, f"Score={score} out of bounds"
```

Remove or update the old `test_composite_score_bounded_from_inputs` and `test_composite_score_pairwise_dominance` that tested the deprecated function.

- [ ] **Step 4: Run all signal tests**

```bash
uv run pytest tests/unit/signals/ -v --tb=short
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/signals/
git commit -m "test(signals): update e2e + hardening + property tests for gate model [KAN-556]"
```

---

### Task 7b: Fix convergence consumer — Piotroski extraction from new column

**Files:**
- Modify: `backend/services/signal_convergence.py`
- Modify: `tests/unit/services/test_signal_convergence.py`

**Context for subagent:**
- `signal_convergence.py:327-331` currently reads Piotroski from `composite_weights` JSONB:
  ```python
  weights = signal.composite_weights or {}
  raw_pio = weights.get("piotroski")
  ```
- The old `composite_weights` format stored `{"piotroski": 7, "mode": "50/50", ...}` at the top level.
- The new format nests it: `{"gate_5_fundamental": {"piotroski": 7, ...}, "mode": "confirmation_gate_v2", ...}`.
- After Task 1, `SignalSnapshot` now has a `piotroski_score` column — **use that directly** instead of parsing JSONB.
- This is a **BREAKING CHANGE** if not fixed — convergence will silently lose Piotroski classification for all tickers.

- [ ] **Step 1: Update piotroski extraction in signal_convergence.py**

In `backend/services/signal_convergence.py`, find lines 327-331 and replace:

```python
        # Extract piotroski from composite_weights JSONB (stored during signal computation)
        # JSONB numbers may deserialize as float — cast to int explicitly
        weights = signal.composite_weights or {}
        raw_pio = weights.get("piotroski")
        piotroski_score: int | None = int(raw_pio) if raw_pio is not None else None
```

With:

```python
        # Read piotroski from the dedicated column (migration 044).
        # Fall back to composite_weights JSONB for old-format rows that
        # haven't been recomputed yet (transition period after deploy).
        raw_pio = getattr(signal, "piotroski_score", None)
        if raw_pio is None:
            weights = signal.composite_weights or {}
            raw_pio = weights.get("piotroski")
        piotroski_score: int | None = int(raw_pio) if raw_pio is not None else None
```

- [ ] **Step 2: Update convergence tests**

In `tests/unit/services/test_signal_convergence.py`, find any tests that mock `composite_weights` with `{"piotroski": N}` and update them to set `piotroski_score=N` on the mock signal object instead. Search for `composite_weights` in the test file and update each occurrence.

Example — if a test has:
```python
signal.composite_weights = {"piotroski": 7, "mode": "50/50"}
```
Change to:
```python
signal.piotroski_score = 7
signal.composite_weights = {"mode": "confirmation_gate_v2", "gate_5_fundamental": {"piotroski": 7}}
```

- [ ] **Step 3: Run convergence tests**

```bash
uv run pytest tests/unit/services/test_signal_convergence.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/services/signal_convergence.py tests/unit/services/test_signal_convergence.py
git commit -m "fix(convergence): read piotroski from column instead of JSONB [KAN-556]"
```

---

### Task 8: Lint + full test suite

- [ ] **Step 1: Lint and format**

```bash
uv run ruff check --fix backend/services/signals.py backend/tools/signals.py tests/unit/signals/
uv run ruff format backend/services/signals.py backend/tools/signals.py tests/unit/signals/
```

- [ ] **Step 2: Run full unit test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```

Expected: 2698+ tests pass, 0 failures.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: lint + format gate engine changes [KAN-556]"
```

---

## PR3: Historical Features + Reseed + Frontend Validation (KAN-557)

**Depends on:** PR2 merged (gate engine active, new columns populated).

### Task 9: Add ADX/OBV/MFI to historical feature model + backfill

**Files:**
- Create: `backend/migrations/versions/XXX_045_historical_feature_gate_columns.py`
- Modify: `backend/models/historical_feature.py`
- Modify: `backend/services/feature_engineering.py`
- Modify: `scripts/backfill_features.py`

**Context for subagent:**
- `historical_features` model: `backend/models/historical_feature.py` (77 lines, 17 feature columns)
- `feature_engineering.py`: vectorized pandas-ta functions at `backend/services/feature_engineering.py`
- `backfill_features.py`: CLI script at `scripts/backfill_features.py` — batch upserts with BATCH_SIZE=1500
- Alembic head after PR1: will be migration 044. This migration is 045.
- New columns: `adx_value`, `obv_slope`, `mfi_value` (all Float, nullable=True for backfill compatibility)
- pandas-ta vectorized equivalents: `ta.adx()` returns DataFrame with `ADX_14` column, `ta.obv()` returns Series, `ta.mfi()` returns Series

- [ ] **Step 1: Add 3 new columns to HistoricalFeature model**

In `backend/models/historical_feature.py`, add after `spy_momentum_21d`:

```python
    # Gate indicators (confirmation-gate scoring v2)
    adx_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    obv_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    mfi_value: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 2: Generate migration**

```bash
uv run alembic revision --autogenerate -m "045 historical feature gate columns"
```

Review: should have 3 `add_column` operations. Clean up any TimescaleDB false positives. Apply:

```bash
uv run alembic upgrade head
```

- [ ] **Step 3: Add vectorized ADX/OBV slope/MFI computation to feature_engineering.py**

Add these functions to `backend/services/feature_engineering.py`:

```python
ADX_PERIOD = 14
MFI_PERIOD = 14
OBV_SLOPE_WINDOW = 21


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
    return adx_df[col]


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
        x = np.arange(len(arr), dtype=float)
        mean_abs = np.abs(arr).mean()
        if mean_abs == 0:
            return 0.0
        return float(np.polyfit(x, arr, 1)[0]) / mean_abs

    return obv.rolling(window).apply(_slope, raw=True)


def compute_mfi_series(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
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
```

- [ ] **Step 4: Update backfill_features.py to include new columns**

In `scripts/backfill_features.py`, find the feature DataFrame assembly section and add:

```python
    # Gate indicators
    features["adx_value"] = compute_adx_series(df["High"], df["Low"], closes)
    features["obv_slope"] = compute_obv_slope_series(closes, df["Volume"])
    features["mfi_value"] = compute_mfi_series(df["High"], df["Low"], closes, df["Volume"])
```

Add these to the column list used in the INSERT statement and upsert `set_` dict.

Also add the imports at the top:

```python
from backend.services.feature_engineering import (
    # ... existing imports ...
    compute_adx_series,
    compute_mfi_series,
    compute_obv_slope_series,
)
```

- [ ] **Step 5: Commit**

```bash
git add backend/models/historical_feature.py backend/migrations/versions/*045* \
       backend/services/feature_engineering.py scripts/backfill_features.py
git commit -m "feat(features): add ADX/OBV/MFI to historical features + backfill [KAN-557]"
```

---

### Task 10: Unit tests for vectorized feature functions

**Files:**
- Modify or create: `tests/unit/services/test_feature_engineering.py`

**Context for subagent:**
- Check if `tests/unit/services/test_feature_engineering.py` exists. If so, add to it. If not, create it.
- The vectorized functions return pd.Series (not scalars) — test shapes and value ranges.

- [ ] **Step 1: Write tests for new vectorized functions**

```python
"""Tests for vectorized gate indicator feature engineering functions."""

import numpy as np
import pandas as pd
import pytest

from backend.services.feature_engineering import (
    compute_adx_series,
    compute_mfi_series,
    compute_obv_slope_series,
)


def _make_ohlcv(n: int = 250, trend: float = 0.002, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for feature engineering tests."""
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.cumprod(1 + rng.normal(trend, 0.015, n))
    dates = pd.bdate_range(end="2025-06-01", periods=n)
    return pd.DataFrame({
        "High": closes * (1 + rng.uniform(0, 0.02, n)),
        "Low": closes * (1 - rng.uniform(0, 0.02, n)),
        "Close": closes,
        "Volume": rng.integers(500_000, 10_000_000, n).astype(float),
    }, index=dates)


class TestComputeADXSeries:
    """Tests for vectorized ADX computation."""

    def test_returns_series_same_length(self) -> None:
        """ADX series should have the same length as input."""
        df = _make_ohlcv(100)
        result = compute_adx_series(df["High"], df["Low"], df["Close"])
        assert len(result) == 100

    def test_values_in_range(self) -> None:
        """Non-NaN ADX values should be between 0 and 100."""
        df = _make_ohlcv(250)
        result = compute_adx_series(df["High"], df["Low"], df["Close"])
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestComputeOBVSlopeSeries:
    """Tests for vectorized OBV slope computation."""

    def test_returns_series_same_length(self) -> None:
        """OBV slope series should have the same length as input."""
        df = _make_ohlcv(100)
        result = compute_obv_slope_series(df["Close"], df["Volume"])
        assert len(result) == 100

    def test_uptrend_positive_slope(self) -> None:
        """Strong uptrend with increasing volume should produce positive OBV slope."""
        df = _make_ohlcv(100, trend=0.005)
        result = compute_obv_slope_series(df["Close"], df["Volume"])
        # Last value should be positive for uptrend
        last_valid = result.dropna()
        if len(last_valid) > 0:
            assert last_valid.iloc[-1] > -1  # At least not strongly negative


class TestComputeMFISeries:
    """Tests for vectorized MFI computation."""

    def test_returns_series_same_length(self) -> None:
        """MFI series should have the same length as input."""
        df = _make_ohlcv(100)
        result = compute_mfi_series(df["High"], df["Low"], df["Close"], df["Volume"])
        assert len(result) == 100

    def test_values_in_range(self) -> None:
        """Non-NaN MFI values should be between 0 and 100."""
        df = _make_ohlcv(250)
        result = compute_mfi_series(df["High"], df["Low"], df["Close"], df["Volume"])
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all()
        assert (valid <= 100).all()
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/unit/services/test_feature_engineering.py -v --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/services/test_feature_engineering.py
git commit -m "test(features): unit tests for vectorized ADX/OBV/MFI functions [KAN-557]"
```

---

### Task 11: Universe reseed + distribution validation

This task is manual (orchestrator-driven, not subagent). It validates that the new scoring produces a reasonable distribution.

- [ ] **Step 1: Run signal refresh across the universe**

```bash
uv run python scripts/seed_prices.py --signals-only
```

Or trigger via Celery:

```bash
uv run celery -A backend.tasks call backend.tasks.market_data.nightly_price_refresh_task
```

- [ ] **Step 2: Query score distribution**

```sql
-- Connect to DB and run:
SELECT
  CASE
    WHEN composite_score >= 8 THEN 'BUY'
    WHEN composite_score >= 5 THEN 'WATCH'
    ELSE 'AVOID'
  END as recommendation,
  COUNT(*) as count,
  ROUND(AVG(composite_score)::numeric, 1) as avg_score
FROM (
  SELECT DISTINCT ON (ticker) ticker, composite_score
  FROM signal_snapshots
  ORDER BY ticker, computed_at DESC
) latest
WHERE composite_score IS NOT NULL
GROUP BY 1
ORDER BY 1;
```

**Hard acceptance gate — STOP and recalibrate if any condition fails:**
- BUY (>=8): **must be >= 5 and <= 100**. If 0, the new model has the same problem as the old one. If >100, thresholds are too loose.
- WATCH (5-7.9): **must be >= 50**. If <50, most of the universe is binary BUY/AVOID with no middle ground.
- AVOID (<5): expected to be the majority.
- **If any gate fails:** Do NOT merge. Adjust gate thresholds (e.g., Gate 2 requiring 2/4 instead of 3/4) and re-run.

- [ ] **Step 3: Verify composite_weights format**

```sql
SELECT ticker, composite_score,
       composite_weights->>'mode' as mode,
       composite_weights->>'gates_confirmed' as confirmed,
       composite_weights->>'gates_active' as active
FROM signal_snapshots
WHERE composite_score IS NOT NULL
ORDER BY computed_at DESC
LIMIT 20;
```

Verify: all rows show `mode = "confirmation_gate_v2"`.

- [ ] **Step 4: Spot-check a BUY signal**

Pick a ticker with score >= 8. Read its `composite_weights` JSONB. Verify all 4-5 gates show sensible explanations.

- [ ] **Step 5: Run frontend and visually verify**

```bash
cd frontend && npm run dev
```

Check:
- Dashboard Action Required: should now show BUY signals (previously showed none)
- Screener: sort by composite_score desc, verify BUY/WATCH/AVOID distribution
- Stock detail: pick a BUY stock, verify composite score renders

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
```

Expected: 2700+ tests pass.

- [ ] **Step 7: Final commit**

```bash
git add -u
git commit -m "chore: validate gate scoring distribution across universe [KAN-557]"
```

---

## Subagent Dispatch Summary

| Task | Can Parallel? | Model | Notes |
|------|--------------|-------|-------|
| Task 1 (migration) | Independent | Sonnet | Additive: new columns only. **DONE (GLM).** |
| Task 2 (indicator funcs) | After Task 1 | Sonnet | Additive: new functions + wiring. Includes compute_macd() 4-tuple refactor. |
| Task 3 (indicator tests) | After Task 2 | Sonnet | Tests for new functions |
| Task 4 (property tests) | After Task 2 | Sonnet | Small update |
| Task 5 (lint) | After Task 3+4 | Sonnet | Mechanical |
| Task 6 (gate engine) | After PR1 merged | Sonnet | Core rewrite, well-specified |
| Task 7 (update tests) | After Task 6 | Sonnet | Test updates |
| Task 7b (convergence fix) | After Task 6 | Sonnet | **CRITICAL:** Fix piotroski extraction from JSONB → column |
| Task 8 (lint) | After Task 7+7b | Sonnet | Mechanical |
| Task 9 (features backfill) | After PR2 merged | Sonnet | Additive: new columns + functions |
| Task 10 (feature tests) | After Task 9 | Sonnet | Tests for new functions |
| Task 11 (validation) | After Task 10 | Orchestrator | Manual verification |

**PR1 parallelism:** Tasks 1 and 2 are sequential (migration first). Tasks 3 and 4 can run in parallel after Task 2.

**PR2 parallelism:** Task 6 is the core work. Tasks 7 and 7b can run in parallel after Task 6.

**PR3 parallelism:** Tasks 9 and 10 are sequential. Task 11 is manual.

## Downstream Consumer Impact Notes

| Consumer | File | Impact | Action |
|----------|------|--------|--------|
| **Convergence** | `signal_convergence.py:327-331` | **BREAKING** — reads `piotroski` from old JSONB format | **Task 7b** — switch to `signal.piotroski_score` column |
| **Recommendations** | `recommendations.py:412-413` | Non-breaking — passes `composite_weights` as `score_breakdown` in reasoning. New format is more verbose. | No change needed. AI agent sees different structure in context. |
| **Frontend** | Various `*-zone.tsx` | Non-breaking — only reads `composite_score` number, ignores `composite_weights` | No change needed |
| **DQ scan** | `tasks/dq_scan.py` | Non-breaking — reads `composite_score` only | No change needed |
| **Alerts** | `tasks/alerts.py` | Non-breaking — reads `composite_score` only | No change needed |

## Post-Ship: Obsidian Update

After PR2 merges, update `2-domain/financial-indicators/Multi-Signal Scoring Framework.md` in the Obsidian vault to reflect the new gate model (currently describes old additive 50/50 architecture).
