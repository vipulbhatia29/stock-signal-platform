# Signal Scoring Overhaul — Confirmation-Gate Pipeline

**Date:** 2026-04-30
**Epic:** KAN-TBD
**Author:** Claude (Opus) + PM design session
**Status:** Draft

---

## Problem Statement

The current composite scoring system (`compute_composite_score()`) averages 4 indicators (RSI, MACD, SMA, Sharpe) into a 0-10 score using additive point assignment. This produces scores that cluster around 3-5, with zero stocks ever reaching the BUY threshold (>=8). The max observed score across 570+ tickers is 7.5.

**Root causes identified through expert research:**

1. **Sharpe ratio is not a signal** — it's a backward-looking risk metric, not a directional indicator. Using it as 25% of buy/sell timing is conceptually wrong.
2. **No volume confirmation** — price moves without volume are unreliable. Academic research (arxiv.org/2206.12282) shows standalone MACD has <50% win rate; adding volume-based indicators (MFI, OBV) significantly improves accuracy.
3. **No trend strength context** — RSI oversold in a strong downtrend (ADX >25) is a falling knife. RSI oversold in a range-bound market (ADX <20) is a valid buy. Our system treats them identically.
4. **Averaging masks disagreement** — RSI bullish + MACD bearish + SMA bearish = score ~4.5 (ambiguous). The expert approach: 1 of 3 confirms = NO signal, not a weak signal.
5. **50/50 Piotroski blend only when data exists** — most tickers fall back to 100% technical, making scores inconsistent across the universe.

## Design: Confirmation-Gate Pipeline

Replace the additive score with a **5-gate confirmation model**. Each gate is binary (confirms or vetoes). The composite score reflects how many gates confirm.

### Gate 1: Trend Regime (ADX)

**Purpose:** Determine whether directional signals are valid.

| ADX Value | Regime | Implication |
|-----------|--------|-------------|
| < 20 | Range-bound | Momentum signals unreliable; mean-reversion valid |
| 20-25 | Emerging trend | Signals becoming valid; lower confidence |
| > 25 | Trending | Directional signals valid; mean-reversion dangerous |

**Data source:** Computed from OHLC via `pandas_ta.adx(high, low, close, length=14)`. Requires `stock_prices.high`, `stock_prices.low`, `stock_prices.close`.

**Confirmed when:** ADX > 20 (a trend exists to trade).

### Gate 2: Direction (MACD + SMA Alignment)

**Purpose:** Confirm which direction the trend is moving and that multiple timeframes agree.

**Conditions for bullish confirmation (ALL must be true):**
- MACD histogram > 0 (short-term momentum positive)
- MACD histogram increasing vs prior day (momentum accelerating, not decelerating)
- Price above 50-day SMA (intermediate trend supports)
- 50-day SMA above 200-day SMA (long-term trend supports)

**Bearish confirmation:** All conditions inverted.

**Data source:** Already computed — `signal_snapshots.macd_histogram`, `sma_50`, `sma_200`. Need to add: prior-day histogram for acceleration check.

**Confirmed when:** At least 3 of 4 directional conditions align.

### Gate 3: Volume Confirmation (OBV trend + MFI)

**Purpose:** Verify that money is actually flowing in the direction of the price move.

| Indicator | Bullish | Bearish |
|-----------|---------|---------|
| OBV | 21-day OBV slope > 0 (rising) | 21-day OBV slope < 0 (falling) |
| MFI | MFI > 50 (net buying pressure) | MFI < 50 (net selling pressure) |

**Data source:** Computed from OHLCV via `pandas_ta.obv(close, volume)` and `pandas_ta.mfi(high, low, close, volume, length=14)`. All inputs exist in `stock_prices`.

**Confirmed when:** Both OBV trend and MFI agree with the direction from Gate 2.

### Gate 4: Entry Timing (RSI, context-aware)

**Purpose:** Determine whether the entry is well-timed (not chasing).

RSI interpretation depends on the regime from Gate 1:

| Regime | Bullish Entry | Bearish Entry |
|--------|---------------|---------------|
| Trending (ADX > 25) | RSI 40-65 (pullback in uptrend) | RSI 35-60 (bounce in downtrend) |
| Range-bound (ADX < 20) | RSI < 35 (oversold mean-reversion) | RSI > 65 (overbought mean-reversion) |
| Emerging (ADX 20-25) | RSI < 50 (not yet extended) | RSI > 50 (not yet washed out) |

**Data source:** Already computed — `signal_snapshots.rsi_value`. ADX from Gate 1.

**Confirmed when:** RSI is in the favorable zone for the current regime + direction.

### Gate 5: Fundamental Health (Piotroski F-Score)

**Purpose:** Filter out value traps — technically bullish stocks with deteriorating fundamentals.

| F-Score | Interpretation |
|---------|---------------|
| >= 7 | Strong fundamentals — full confirmation |
| 4-6 | Neutral — does not veto, does not confirm (gate passes as neutral) |
| 0-3 | Weak fundamentals — vetoes bullish signal |
| NULL | No data (ETFs, new listings) — gate skipped, not counted |

**Data source:** Computed on-demand from yfinance in `stock_data.py`. Currently transient — needs to be persisted in `signal_snapshots` or `stocks` table.

**Confirmed when:** F-Score >= 7, OR F-Score 4-6 (neutral pass), OR no data available (skip).
**Vetoed when:** F-Score 0-3 AND direction is bullish.

### Score Computation

```
active_gates = count of gates that had enough data to evaluate (typically 5, fewer for ETFs/new listings)
confirmed_gates = count of gates that confirmed

composite_score = round((confirmed_gates / active_gates) * 10, 1)
```

| Confirmed / Active | Score | Recommendation |
|--------------------|-------|----------------|
| 5/5 or 4/4 | 10.0 | **BUY** — all signals confirm |
| 4/5 | 8.0 | **BUY** — strong confirmation |
| 3/5 or 3/4 | 6.0-7.5 | **WATCH** — majority confirm but gaps |
| 2/5 | 4.0 | **AVOID** — weak confirmation |
| 1/5 or 0/5 | 0.0-2.0 | **AVOID** — no confirmation |

**Threshold re-calibration:**
- BUY: score >= 8 (4+ of 5 gates confirm) — unchanged threshold, but now achievable
- WATCH: score >= 5 (3 of 5 gates confirm)
- AVOID: score < 5 (fewer than 3 gates)

### Additional Output: `signal_explanation`

Each gate produces a one-line human-readable explanation stored in `composite_weights` JSONB:

```json
{
  "mode": "confirmation_gate_v2",
  "gates_active": 5,
  "gates_confirmed": 4,
  "gate_1_trend": {"confirmed": true, "adx": 32.5, "regime": "trending", "detail": "Strong trend (ADX 32.5)"},
  "gate_2_direction": {"confirmed": true, "macd_accel": true, "sma_aligned": true, "detail": "Bullish MACD accelerating, above 50/200 SMA"},
  "gate_3_volume": {"confirmed": true, "obv_slope": 0.15, "mfi": 62.3, "detail": "Money flowing in (MFI 62, OBV rising)"},
  "gate_4_entry": {"confirmed": false, "rsi": 72, "regime": "trending", "detail": "RSI 72 — chasing, wait for pullback to 40-65"},
  "gate_5_fundamental": {"confirmed": true, "piotroski": 7, "detail": "Strong fundamentals (F-Score 7/9)"}
}
```

## Schema Changes

### Migration: Add columns to `signal_snapshots`

```sql
ALTER TABLE signal_snapshots ADD COLUMN adx_value FLOAT;
ALTER TABLE signal_snapshots ADD COLUMN obv_slope FLOAT;       -- 21-day OBV linear regression slope
ALTER TABLE signal_snapshots ADD COLUMN mfi_value FLOAT;        -- Money Flow Index (0-100)
ALTER TABLE signal_snapshots ADD COLUMN atr_value FLOAT;        -- Average True Range (for future use)
ALTER TABLE signal_snapshots ADD COLUMN piotroski_score INTEGER; -- Persisted F-Score (0-9)
ALTER TABLE signal_snapshots ADD COLUMN macd_histogram_prev FLOAT; -- Prior day histogram for acceleration
```

### Model changes: `backend/models/signal.py`

Add 6 new `mapped_column` fields matching the migration.

### No new tables needed.

## Files Changed

| File | Change |
|------|--------|
| `backend/services/signals.py` | Rewrite `compute_composite_score()` → `compute_confirmation_gates()`. Add ADX/OBV/MFI/ATR computation in `compute_signals()`. |
| `backend/models/signal.py` | Add 6 new columns |
| `backend/migrations/versions/XXX.py` | Migration for new columns |
| `backend/services/recommendations.py` | Thresholds stay the same (BUY >= 8, WATCH >= 5) — distribution changes |
| `backend/services/feature_engineering.py` | Add ADX/OBV/MFI to historical feature builder |
| `backend/models/historical_feature.py` | Add new feature columns |
| `scripts/backfill_features.py` | Include new indicators in backfill |
| `tests/unit/services/test_signals.py` | Rewrite composite score tests for gate model |
| `tests/unit/services/test_recommendations.py` | Verify recommendation distribution |
| Frontend: `action-required-zone.tsx` | Threshold may need re-tuning (currently 8 for BUY) |

## Implementation Plan (3 PRs)

### PR1: Schema + Computation (~0.5 day)
- Migration: add 6 columns to `signal_snapshots`
- Add ADX, OBV, MFI, ATR computation to `compute_signals()` using pandas-ta
- Persist Piotroski score in signal snapshot
- Store `macd_histogram_prev` (prior day value)
- Unit tests for new indicator computation

### PR2: Gate Engine + Score Rewrite (~1 day)
- Replace `compute_composite_score()` with `compute_confirmation_gates()`
- Gate logic for all 5 gates with regime-aware RSI
- `composite_weights` JSONB output with per-gate explanations
- Score = `(confirmed / active) * 10`
- Rewrite all composite score unit tests
- Validate score distribution across full universe (expect: 5-15 BUY, 80-120 WATCH, rest AVOID)

### PR3: Backfill + Frontend (~0.5 day)
- Re-run `seed_prices --universe` to recompute signals with new indicators
- Update `backfill_features.py` to include ADX/OBV/MFI in historical features
- Verify Action Required section shows realistic BUY/SELL split
- Verify screener, stock detail, sectors pages render correctly with new scores

## Acceptance Criteria

1. `compute_signals()` computes and persists ADX, OBV slope, MFI, ATR, Piotroski for every ticker
2. `composite_score` is computed via 5-gate confirmation model, not additive averaging
3. Score of 8+ (BUY) means 4+ of 5 gates confirmed — achievable but selective (~2-5% of universe)
4. Score of 0-4 (AVOID) means fewer than 3 gates confirmed — majority of universe in bearish markets
5. `composite_weights` JSONB contains per-gate explanations (human-readable)
6. All existing consumers (dashboard, screener, sectors, stock detail, recommendations, convergence, chat) work unchanged — they read the same 0-10 score
7. Action Required section shows a realistic mix of BUY and SELL signals
8. All existing signal tests updated, no regressions

## Risk: Score Distribution Shift

The main risk is that the new scoring produces a very different distribution than the old one. Downstream consumers (alerts < 4, convergence labels, recommendation thresholds) were calibrated to the old distribution. Mitigation:

- PR2 includes a universe-wide distribution analysis before merging
- If the distribution is dramatically different, thresholds are re-calibrated in the same PR
- The `composite_weights.mode` field (`"confirmation_gate_v2"`) lets us identify which scoring version produced a given snapshot

## References

- [Assessing the Impact of Technical Indicators on ML Models](https://arxiv.org/html/2412.15448v1) — feature importance, individual vs combined effectiveness
- [MACD Trading Strategies Comparative Study](https://arxiv.org/abs/2206.12282) — MACD <50% win rate alone, volume improves it
- [Piotroski Fscore under Varying Economic Conditions](https://link.springer.com/article/10.1007/s11156-024-01331-y) — F-score + momentum = 15% annual alpha
- [Schwab: ADX + RSI Combined Methodology](https://www.schwab.com/learn/story/spot-and-stick-to-trends-with-adx-and-rsi)
- [Fidelity: Understanding Technical Indicators](https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/learning-center/Understanding-Indicators-TA.pdf)
