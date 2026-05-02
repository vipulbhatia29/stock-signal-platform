# Unified Chart with Indicator Overlays — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the disconnected price chart + signal cards with a unified lightweight-charts instance showing SMA overlays, Bollinger bands, RSI/MACD sub-panels, and a compact legend strip — all with zoom/pan/crosshair.

**Architecture:** New backend endpoint `/stocks/{ticker}/prices/with-indicators` returns OHLC + computed indicator time series. Frontend rewrites `price-chart.tsx` to use lightweight-charts for both Line and Candle modes with SMA/BB overlays and toggleable RSI/MACD panes. Signal Breakdown cards replaced by compact legend strip. Signal History chart replaced by RSI sub-panel.

**Tech Stack:** lightweight-charts v5.1.0 (already installed), pandas-ta (backend), TanStack Query, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-05-02-unified-chart-with-indicators.md`

---

## Fact Sheet

```
Backend price endpoint: backend/routers/stocks/data.py:110-175 (get_prices)
Price schema: backend/schemas/stock.py — PricePointResponse (line 61), OHLCResponse (line 111)
Signal constants: backend/services/signals.py — RSI_PERIOD=14, MACD_FAST=12, MACD_SLOW=26, MACD_SIGNAL=9, SMA_SHORT=50, SMA_LONG=200, BB_PERIOD=20, BB_STD_DEV=2
Feature engineering: backend/services/feature_engineering.py — vectorized compute_rsi_series, compute_macd_histogram_series, compute_sma_cross_series, compute_bb_position_series

Frontend price chart: frontend/src/components/price-chart.tsx — PriceChart component (Recharts line + dynamic CandlestickChart)
Candlestick chart: frontend/src/components/candlestick-chart.tsx — lightweight-charts CandlestickSeries + HistogramSeries (volume)
Signal cards: frontend/src/components/signal-cards.tsx — 4 full-width cards (RSI, MACD, SMA, Bollinger)
Signal history: frontend/src/components/signal-history-chart.tsx — Recharts ComposedChart (90-day composite + RSI)
Stock detail page: frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx
Hooks: frontend/src/hooks/use-stocks.ts — usePrices (line 201), useOHLC (line 354), useSignals
Types: frontend/src/types/api.ts — PricePoint (line 55), OHLCResponse (line 1019), SignalResponse (line 104)
Chart theme: frontend/src/lib/lightweight-chart-theme.ts — useLightweightChartTheme()
Chart colors: frontend/src/lib/chart-theme.ts — useChartColors() with sma50, sma200, rsi CSS vars
Design tokens: frontend/src/lib/design-tokens.ts — chartSma50, chartSma200, chartRsi (lines 32-34)
Test mocks: frontend/src/__tests__/integration/stock-detail.test.tsx — SignalCards mock (line 101), SignalHistoryChart mock (line 69)

lightweight-charts API (from typings.d.ts):
  chart.addSeries(definition, options?, paneIndex?) — add series to specific pane
  chart.addPane(preserveEmptyPane?) — create new pane, returns IPaneApi
  chart.panes() — list all panes
  pane.addSeries(definition, options?) — add series to pane
  createSeriesMarkers(series, markers?) — golden/death cross annotations
```

---

## PR1: Backend Indicator Endpoint + Frontend Chart Rewrite with SMA Overlays + Legend Strip

### Task 1: Backend — Response schema for price-with-indicators

**Files:**
- Modify: `backend/schemas/stock.py`

- [ ] **Step 1: Add indicator response schemas**

Add after `OHLCResponse` (line 127):

```python
class IndicatorSeries(BaseModel):
    """Pre-computed technical indicator time series, aligned with price array."""

    sma_50: list[float | None] | None = None
    sma_200: list[float | None] | None = None
    bb_upper: list[float | None] | None = None
    bb_lower: list[float | None] | None = None
    bb_middle: list[float | None] | None = None
    rsi: list[float | None] | None = None
    macd_histogram: list[float | None] | None = None
    macd_line: list[float | None] | None = None
    macd_signal: list[float | None] | None = None


class PriceWithIndicatorsResponse(BaseModel):
    """OHLCV prices with optional aligned indicator series."""

    ticker: str
    period: str
    count: int
    prices: list[PricePointResponse]
    indicators: IndicatorSeries
```

- [ ] **Step 2: Commit**

```bash
git add backend/schemas/stock.py
git commit -m "feat(schema): add PriceWithIndicatorsResponse for chart overlays [KAN-559]"
```

---

### Task 2: Backend — Indicator computation service function

**Files:**
- Modify: `backend/services/feature_engineering.py`

**Context for subagent:**
- This file already has `compute_rsi_series`, `compute_macd_histogram_series`, `compute_sma_cross_series`, `compute_bb_position_series`, `compute_adx_series`, `compute_obv_slope_series`, `compute_mfi_series`.
- We need a new function that takes an OHLCV DataFrame and returns a dict of indicator arrays.
- Reuse existing constants: `RSI_PERIOD`, `MACD_FAST`, `MACD_SLOW`, `MACD_SIGNAL`, `SMA_SHORT`, `SMA_LONG`, `BB_PERIOD`, `BB_STD_DEV`.
- SMA values are needed as raw float series (not the 0/1/2 cross encoding). Use `ta.sma()` directly.
- MACD needs histogram + line + signal (not just histogram). Use `ta.macd()` which returns a DataFrame with columns `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9`.
- pandas-ta needs `import importlib.metadata` before `import pandas_ta` (already at top of file).
- NaN → None conversion for JSON serialization.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/services/test_indicator_series.py`:

```python
"""Tests for compute_indicator_series — chart overlay data."""

import numpy as np
import pandas as pd
import pytest


def _make_ohlcv(n: int = 250, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.cumprod(1 + rng.normal(0.001, 0.015, n))
    dates = pd.bdate_range(end="2025-06-01", periods=n)
    return pd.DataFrame(
        {
            "close": closes,
            "high": closes * (1 + rng.uniform(0, 0.02, n)),
            "low": closes * (1 - rng.uniform(0, 0.02, n)),
            "volume": rng.integers(500_000, 10_000_000, n).astype(float),
        },
        index=dates,
    )


class TestComputeIndicatorSeries:
    """Tests for compute_indicator_series()."""

    def test_returns_all_requested_indicators(self) -> None:
        """When all indicators requested, all keys are present."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(250)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators={"sma", "bb", "rsi", "macd"},
        )
        assert "sma_50" in result
        assert "sma_200" in result
        assert "bb_upper" in result
        assert "rsi" in result
        assert "macd_histogram" in result

    def test_arrays_aligned_with_input_length(self) -> None:
        """All indicator arrays must have the same length as input."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(250)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators={"sma", "rsi"},
        )
        assert len(result["sma_50"]) == 250
        assert len(result["rsi"]) == 250

    def test_only_requested_indicators_returned(self) -> None:
        """When only 'sma' requested, no rsi/macd/bb keys."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(250)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators={"sma"},
        )
        assert "sma_50" in result
        assert "rsi" not in result
        assert "macd_histogram" not in result
        assert "bb_upper" not in result

    def test_warmup_values_are_none(self) -> None:
        """First ~200 rows of SMA 200 should be None (warmup)."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(250)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators={"sma"},
        )
        # SMA 200 needs 200 data points before producing a value
        assert result["sma_200"][0] is None
        assert result["sma_200"][100] is None
        # Last values should be float
        assert isinstance(result["sma_200"][-1], float)

    def test_sma_values_reasonable(self) -> None:
        """SMA values should be within price range."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(300)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators={"sma"},
        )
        valid_sma50 = [v for v in result["sma_50"] if v is not None]
        assert len(valid_sma50) > 0
        assert all(50.0 < v < 200.0 for v in valid_sma50)

    def test_rsi_values_in_range(self) -> None:
        """Non-None RSI values should be between 0 and 100."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(250)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators={"rsi"},
        )
        valid_rsi = [v for v in result["rsi"] if v is not None]
        assert len(valid_rsi) > 0
        assert all(0 <= v <= 100 for v in valid_rsi)

    def test_empty_indicators_set_returns_empty_dict(self) -> None:
        """Empty indicators set returns empty dict."""
        from backend.services.feature_engineering import compute_indicator_series

        df = _make_ohlcv(100)
        result = compute_indicator_series(
            df["close"], df["high"], df["low"], df["volume"],
            indicators=set(),
        )
        assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/services/test_indicator_series.py -v --tb=short
```

Expected: `ImportError: cannot import name 'compute_indicator_series'`

- [ ] **Step 3: Implement `compute_indicator_series`**

Add to `backend/services/feature_engineering.py` after `compute_mfi_series`:

```python
def compute_indicator_series(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    *,
    indicators: set[str],
) -> dict[str, list[float | None]]:
    """Compute requested indicator time series aligned with input.

    Args:
        close: Closing prices.
        high: High prices.
        low: Low prices.
        volume: Volume data.
        indicators: Set of indicator keys to compute.
            Valid keys: "sma", "bb", "rsi", "macd".

    Returns:
        Dict mapping indicator names to arrays of float|None,
        same length as input. NaN values converted to None for
        JSON serialization.
    """
    n = len(close)
    result: dict[str, list[float | None]] = {}

    def _to_list(s: pd.Series) -> list[float | None]:
        return [round(float(v), 4) if pd.notna(v) else None for v in s]

    if "sma" in indicators:
        sma50 = ta.sma(close, length=SMA_SHORT)  # type: ignore[attr-defined]
        sma200 = ta.sma(close, length=SMA_LONG)  # type: ignore[attr-defined]
        result["sma_50"] = _to_list(sma50) if sma50 is not None else [None] * n
        result["sma_200"] = _to_list(sma200) if sma200 is not None else [None] * n

    if "bb" in indicators:
        bb = ta.bbands(close, length=BB_PERIOD, std=BB_STD_DEV)  # type: ignore[attr-defined]
        if bb is not None and not bb.empty:
            result["bb_upper"] = _to_list(bb[f"BBU_{BB_PERIOD}_{BB_STD_DEV}.0"])
            result["bb_lower"] = _to_list(bb[f"BBL_{BB_PERIOD}_{BB_STD_DEV}.0"])
            result["bb_middle"] = _to_list(bb[f"BBM_{BB_PERIOD}_{BB_STD_DEV}.0"])
        else:
            result["bb_upper"] = [None] * n
            result["bb_lower"] = [None] * n
            result["bb_middle"] = [None] * n

    if "rsi" in indicators:
        rsi = ta.rsi(close, length=RSI_PERIOD)  # type: ignore[attr-defined]
        result["rsi"] = _to_list(rsi) if rsi is not None else [None] * n

    if "macd" in indicators:
        macd_df = ta.macd(close, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)  # type: ignore[attr-defined]
        if macd_df is not None and not macd_df.empty:
            result["macd_line"] = _to_list(
                macd_df[f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
            )
            result["macd_histogram"] = _to_list(
                macd_df[f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
            )
            result["macd_signal"] = _to_list(
                macd_df[f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"]
            )
        else:
            result["macd_line"] = [None] * n
            result["macd_histogram"] = [None] * n
            result["macd_signal"] = [None] * n

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/services/test_indicator_series.py -v --tb=short
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/feature_engineering.py tests/unit/services/test_indicator_series.py
git commit -m "feat(features): compute_indicator_series for chart overlays [KAN-559]"
```

---

### Task 3: Backend — New price-with-indicators endpoint

**Files:**
- Modify: `backend/routers/stocks/data.py`

**Context for subagent:**
- The existing `get_prices` endpoint is at line 110. Add the new endpoint AFTER it.
- Route: `GET /{ticker}/prices/with-indicators`
- Must be defined BEFORE `/{ticker}/signals` to avoid path shadowing (FastAPI matches routes in order).
- Query params: `period` (PricePeriod), `indicators` (comma-separated string, required).
- Reuse the same price-loading logic from `get_prices` (query StockPrice, same period_days dict).
- The endpoint loads OHLCV, converts to pandas Series, calls `compute_indicator_series`, and returns `PriceWithIndicatorsResponse`.
- Import `compute_indicator_series` from `backend.services.feature_engineering`.

- [ ] **Step 1: Write the endpoint**

Add after `get_prices` in `backend/routers/stocks/data.py`:

```python
@router.get(
    "/{ticker}/prices/with-indicators",
    response_model=PriceWithIndicatorsResponse,
)
async def get_prices_with_indicators(
    ticker: TickerPath,
    period: PricePeriod = Query(
        default=PricePeriod.ONE_YEAR,
        description="How far back to fetch prices",
    ),
    indicators: str = Query(
        description="Comma-separated indicator keys: sma,bb,rsi,macd",
    ),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PriceWithIndicatorsResponse:
    """Get OHLCV prices with pre-computed indicator time series for chart overlays.

    Indicators are computed server-side using pandas-ta and returned as
    arrays aligned with the prices array. Only requested indicators are
    included — pass a comma-separated list in the `indicators` parameter.
    """
    await require_stock(ticker, db)

    period_days = {
        PricePeriod.ONE_MONTH: 30,
        PricePeriod.THREE_MONTHS: 90,
        PricePeriod.SIX_MONTHS: 180,
        PricePeriod.ONE_YEAR: 365,
        PricePeriod.TWO_YEARS: 730,
        PricePeriod.FIVE_YEARS: 1825,
        PricePeriod.TEN_YEARS: 3650,
    }
    # Fetch extra warmup data for SMA-200 (200 trading days ≈ 280 calendar days)
    warmup_days = 280
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=period_days[period] + warmup_days
    )

    result = await db.execute(
        select(StockPrice)
        .where(StockPrice.ticker == ticker.upper())
        .where(StockPrice.time >= cutoff)
        .order_by(StockPrice.time.asc())
    )
    rows = list(result.scalars().all())

    # Parse requested indicators
    indicator_set = {s.strip().lower() for s in indicators.split(",") if s.strip()}
    valid_keys = {"sma", "bb", "rsi", "macd"}
    indicator_set = indicator_set & valid_keys

    # Build pandas Series for computation
    import pandas as pd

    closes = pd.Series([float(r.close) for r in rows], name="close")
    highs = pd.Series([float(r.high) for r in rows], name="high")
    lows = pd.Series([float(r.low) for r in rows], name="low")
    volumes = pd.Series([float(r.volume) for r in rows], name="volume")

    from backend.services.feature_engineering import compute_indicator_series

    indicator_data = compute_indicator_series(
        closes, highs, lows, volumes, indicators=indicator_set
    )

    # Trim warmup rows — only return the requested period
    visible_cutoff = datetime.now(timezone.utc) - timedelta(days=period_days[period])
    visible_start = 0
    for i, r in enumerate(rows):
        if r.time >= visible_cutoff:
            visible_start = i
            break

    visible_rows = rows[visible_start:]
    trimmed_indicators = {
        k: v[visible_start:] for k, v in indicator_data.items()
    }

    from backend.schemas.stock import IndicatorSeries

    return PriceWithIndicatorsResponse(
        ticker=ticker.upper(),
        period=period.value,
        count=len(visible_rows),
        prices=visible_rows,
        indicators=IndicatorSeries(**trimmed_indicators),
    )
```

Add these imports at the top of the file:

```python
from backend.schemas.stock import PriceWithIndicatorsResponse
```

- [ ] **Step 2: Run lint**

```bash
uv run ruff check backend/routers/stocks/data.py --fix && uv run ruff format backend/routers/stocks/data.py
```

- [ ] **Step 3: Write endpoint test**

Add to `tests/unit/routers/test_stock_data.py` (or create if needed):

```python
@pytest.mark.asyncio
async def test_prices_with_indicators_returns_sma(client, auth_headers, seed_stock):
    """Price-with-indicators endpoint returns SMA arrays aligned with prices."""
    response = await client.get(
        f"/api/v1/stocks/{seed_stock}/prices/with-indicators?period=1y&indicators=sma",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "prices" in data
    assert "indicators" in data
    assert len(data["indicators"]["sma_50"]) == data["count"]
    assert len(data["indicators"]["sma_200"]) == data["count"]
    # RSI/MACD should not be present when not requested
    assert data["indicators"].get("rsi") is None
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/stocks/data.py backend/schemas/stock.py tests/
git commit -m "feat(api): GET /prices/with-indicators endpoint for chart overlays [KAN-559]"
```

---

### Task 4: Frontend — TypeScript types + new hook

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/hooks/use-stocks.ts`

- [ ] **Step 1: Add TypeScript types**

Add to `frontend/src/types/api.ts` after `OHLCResponse`:

```typescript
// ── Price with Indicators ─────────────────────────────────────────────────────

export interface IndicatorSeries {
  sma_50?: (number | null)[];
  sma_200?: (number | null)[];
  bb_upper?: (number | null)[];
  bb_lower?: (number | null)[];
  bb_middle?: (number | null)[];
  rsi?: (number | null)[];
  macd_histogram?: (number | null)[];
  macd_line?: (number | null)[];
  macd_signal?: (number | null)[];
}

export interface PriceWithIndicatorsResponse {
  ticker: string;
  period: string;
  count: number;
  prices: PricePoint[];
  indicators: IndicatorSeries;
}
```

- [ ] **Step 2: Add `usePricesWithIndicators` hook**

Add to `frontend/src/hooks/use-stocks.ts`:

```typescript
export function usePricesWithIndicators(
  ticker: string,
  period: PricePeriod,
  indicators: string = "sma",
) {
  return useQuery({
    queryKey: ["prices-indicators", ticker, period, indicators],
    queryFn: () =>
      get<PriceWithIndicatorsResponse>(
        `/stocks/${ticker}/prices/with-indicators?period=${period}&indicators=${indicators}`
      ),
    staleTime: 5 * 60 * 1000,
  });
}
```

Add `PriceWithIndicatorsResponse` to the import from `@/types/api`.

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/types/api.ts src/hooks/use-stocks.ts
git commit -m "feat(hooks): usePricesWithIndicators hook + types [KAN-559]"
```

---

### Task 5: Frontend — Indicator legend strip component

**Files:**
- Create: `frontend/src/components/indicator-legend-strip.tsx`

**Context for subagent:**
- This is a row of pill-shaped badges showing current indicator values + plain-English labels.
- Data source: `SignalResponse` from `useSignals()` (same data as current signal cards).
- Also shows gate composite score + recommendation label.
- Always visible above the chart.
- Each pill has a subtle colored border. Use Tailwind classes.
- Colors: RSI → purple, MACD → green/red based on signal, SMA → amber, BB → blue, ADX → green, Gate Score → purple.
- Must handle loading state (skeleton pills) and null values gracefully.

- [ ] **Step 1: Create the component**

```typescript
"use client";

import type { SignalResponse } from "@/types/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface IndicatorLegendStripProps {
  signals: SignalResponse | undefined;
  isLoading: boolean;
}

function Pill({
  label,
  value,
  interpretation,
  borderColor,
  textColor,
}: {
  label: string;
  value: string;
  interpretation: string;
  borderColor: string;
  textColor: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs",
        borderColor
      )}
    >
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
      <span className={cn("text-[10px]", textColor)}>{interpretation}</span>
    </div>
  );
}

function getRecommendation(score: number | null): string {
  if (score === null) return "—";
  if (score >= 8) return "BUY";
  if (score >= 5) return "WATCH";
  return "AVOID";
}

function getRsiInterpretation(value: number | null, signal: string | null): string {
  if (value === null) return "—";
  if (signal === "OVERSOLD") return "Oversold";
  if (signal === "OVERBOUGHT") return "Overbought";
  return "Neutral";
}

function getMacdInterpretation(signal: string | null): string {
  if (signal === "BULLISH") return "Bullish";
  if (signal === "BEARISH") return "Bearish";
  return "—";
}

function getSmaInterpretation(signal: string | null): string {
  if (signal === "GOLDEN_CROSS") return "Golden Cross";
  if (signal === "DEATH_CROSS") return "Death Cross";
  if (signal === "ABOVE_200") return "Above 200";
  if (signal === "BELOW_200") return "Below 200";
  return "—";
}

function getBollingerInterpretation(position: string | null): string {
  if (position === "UPPER") return "Upper";
  if (position === "LOWER") return "Lower";
  return "Middle";
}

export function IndicatorLegendStrip({ signals, isLoading }: IndicatorLegendStripProps) {
  if (isLoading) {
    return (
      <div className="flex gap-2 flex-wrap">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-28 rounded-full" />
        ))}
      </div>
    );
  }

  if (!signals) return null;

  const isMacdBullish = signals.macd.signal === "BULLISH";

  return (
    <div className="flex gap-2 flex-wrap">
      <Pill
        label="RSI"
        value={signals.rsi.value?.toFixed(1) ?? "—"}
        interpretation={getRsiInterpretation(signals.rsi.value, signals.rsi.signal)}
        borderColor="border-purple-500/30"
        textColor="text-purple-400"
      />
      <Pill
        label="MACD"
        value={signals.macd.histogram?.toFixed(2) ?? "—"}
        interpretation={getMacdInterpretation(signals.macd.signal)}
        borderColor={isMacdBullish ? "border-green-500/30" : "border-red-500/30"}
        textColor={isMacdBullish ? "text-green-400" : "text-red-400"}
      />
      <Pill
        label="SMA"
        value={getSmaInterpretation(signals.sma.signal)}
        interpretation={`50: ${signals.sma.sma_50?.toFixed(0) ?? "—"} · 200: ${signals.sma.sma_200?.toFixed(0) ?? "—"}`}
        borderColor="border-amber-500/30"
        textColor="text-amber-400"
      />
      <Pill
        label="BB"
        value={`${signals.bollinger.lower?.toFixed(0) ?? "—"}–${signals.bollinger.upper?.toFixed(0) ?? "—"}`}
        interpretation={getBollingerInterpretation(signals.bollinger.position)}
        borderColor="border-blue-400/30"
        textColor="text-blue-400"
      />
      <Pill
        label="Score"
        value={signals.composite_score?.toFixed(1) ?? "—"}
        interpretation={getRecommendation(signals.composite_score)}
        borderColor="border-purple-500/30"
        textColor={
          signals.composite_score !== null && signals.composite_score >= 8
            ? "text-green-400"
            : signals.composite_score !== null && signals.composite_score >= 5
              ? "text-amber-400"
              : "text-red-400"
        }
      />
    </div>
  );
}
```

- [ ] **Step 2: Write test**

Create `frontend/src/__tests__/components/indicator-legend-strip.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { IndicatorLegendStrip } from "@/components/indicator-legend-strip";
import type { SignalResponse } from "@/types/api";

const mockSignals: SignalResponse = {
  ticker: "AAPL",
  computed_at: "2026-05-01T00:00:00Z",
  rsi: { value: 66.4, signal: "NEUTRAL" },
  macd: { value: 4.36, histogram: 0.91, signal: "BULLISH" },
  sma: { sma_50: 261, sma_200: 255, signal: "ABOVE_200" },
  bollinger: { upper: 280, lower: 253, position: "UPPER" },
  returns: { annual_return: 0.15, volatility: 0.2, sharpe: 1.5 },
  composite_score: 7.5,
  current_price: 270,
  change_pct: 1.2,
  market_cap: 3000000000000,
  is_stale: false,
  is_refreshing: false,
};

describe("IndicatorLegendStrip", () => {
  it("renders all indicator pills", () => {
    render(<IndicatorLegendStrip signals={mockSignals} isLoading={false} />);
    expect(screen.getByText("RSI")).toBeInTheDocument();
    expect(screen.getByText("MACD")).toBeInTheDocument();
    expect(screen.getByText("SMA")).toBeInTheDocument();
    expect(screen.getByText("BB")).toBeInTheDocument();
    expect(screen.getByText("Score")).toBeInTheDocument();
  });

  it("shows loading skeletons when isLoading", () => {
    const { container } = render(
      <IndicatorLegendStrip signals={undefined} isLoading={true} />
    );
    const skeletons = container.querySelectorAll("[class*='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders null when no signals and not loading", () => {
    const { container } = render(
      <IndicatorLegendStrip signals={undefined} isLoading={false} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("shows correct MACD interpretation", () => {
    render(<IndicatorLegendStrip signals={mockSignals} isLoading={false} />);
    expect(screen.getByText("Bullish")).toBeInTheDocument();
  });

  it("shows correct SMA interpretation", () => {
    render(<IndicatorLegendStrip signals={mockSignals} isLoading={false} />);
    expect(screen.getByText("Above 200")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run test**

```bash
cd frontend && npx jest src/__tests__/components/indicator-legend-strip.test.tsx --no-coverage
```

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/components/indicator-legend-strip.tsx src/__tests__/components/indicator-legend-strip.test.tsx
git commit -m "feat(ui): indicator legend strip component [KAN-559]"
```

---

### Task 6: Frontend — Rewrite price-chart.tsx with lightweight-charts + SMA overlays

**Files:**
- Rewrite: `frontend/src/components/price-chart.tsx`
- Modify: `frontend/src/components/candlestick-chart.tsx` (may absorb or keep as-is)
- Modify: `frontend/src/lib/lightweight-chart-theme.ts`

**Context for subagent:**
- This is the largest task. Replace the entire PriceChart component.
- Currently uses Recharts for line mode and dynamically imports CandlestickChart for candle mode.
- New version: single lightweight-charts instance for BOTH modes.
- Line mode: use `LineSeries` from lightweight-charts.
- Candle mode: use `CandlestickSeries` (existing pattern in candlestick-chart.tsx).
- Always overlay SMA 50 (orange solid) and SMA 200 (red dashed) as `LineSeries`.
- Volume histogram below price (existing pattern).
- Data source: `usePricesWithIndicators(ticker, period, indicatorString)` replacing both `usePrices` + `useOHLC`.
- The `indicatorString` changes based on toggles: always includes "sma", adds "bb" when Bollinger toggled on, adds "rsi,macd" when Technical Panels toggled on.
- Golden cross / death cross detection: client-side from SMA arrays. Use `createSeriesMarkers()` from lightweight-charts.
- Keep the toolbar: Line/Candle toggle + period selector + Bollinger toggle + Technical Panels toggle.
- Pass `signals` and `isLoading` down from parent for the legend strip.
- The `IndicatorLegendStrip` renders between toolbar and chart.
- lightweight-charts theme from `useLightweightChartTheme()`.
- Chart colors (SMA 50 orange, SMA 200 red) from `useChartColors()`.
- Use `ResizeObserver` for responsive sizing (existing pattern in candlestick-chart.tsx).
- `chart.timeScale().fitContent()` after setting data.

**Important lightweight-charts v5 API notes:**
- `import { createChart, LineSeries, CandlestickSeries, HistogramSeries, AreaSeries } from "lightweight-charts";`
- `createSeriesMarkers` is a named export: `import { createSeriesMarkers } from "lightweight-charts";`
- `chart.addSeries(LineSeries, { color, lineWidth, lineStyle, priceScaleId })` — lineStyle: 0=solid, 2=dashed
- `chart.addSeries(AreaSeries, { topColor, bottomColor, lineColor })` — for Bollinger fill
- Markers: `createSeriesMarkers(series, [{ time, position, shape, color, text }])`

This task produces the core chart rewrite. Sub-panels (RSI/MACD panes) are Task 7 (PR2).

- [ ] **Step 1: Implement the new PriceChart**

Rewrite `frontend/src/components/price-chart.tsx`. The full implementation should:

1. Replace `usePrices` + `useOHLC` with `usePricesWithIndicators`
2. Create a single lightweight-charts instance via `createChart()`
3. Based on `chartMode`, add either `CandlestickSeries` or `LineSeries` for price
4. Add `LineSeries` for SMA 50 (orange, solid) and SMA 200 (red, dashed)
5. Add `HistogramSeries` for volume
6. When Bollinger toggled on, request "sma,bb" and add `AreaSeries` for BB fill
7. Detect golden/death crosses from SMA arrays and add markers
8. Render `IndicatorLegendStrip` between toolbar and chart
9. Use `useEffect` with cleanup (chart.remove()) on data/mode changes
10. Keep period selector and Line/Candle toggle
11. Add Bollinger and Technical Panels toggle buttons

- [ ] **Step 2: Update stock-detail-client.tsx**

Remove imports of `SignalCards` and `SignalHistoryChart`. Remove the "Signal Breakdown" and "Signal History" sections. The `IndicatorLegendStrip` is now rendered inside `PriceChart`.

Update the `SectionNav` items to remove "Signals" and "History" entries (or rename).

- [ ] **Step 3: Update test mocks**

In `frontend/src/__tests__/integration/stock-detail.test.tsx`:
- Remove the `SignalCards` mock (line 101-103)
- Remove the `SignalHistoryChart` mock (line 69-71)
- Add mock for `IndicatorLegendStrip` if needed
- Update any assertions that reference removed sections

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx jest --no-coverage && npx tsc --noEmit
```

- [ ] **Step 5: Lint**

```bash
cd frontend && npm run lint
```

- [ ] **Step 6: Commit**

```bash
cd frontend && git add .
git commit -m "feat(chart): unified lightweight-charts with SMA overlays + legend strip [KAN-559]"
```

---

## PR2: RSI/MACD Sub-Panels + Bollinger Toggle + Tests

### Task 7: Frontend — RSI and MACD sub-panels (Technical Panels toggle)

**Files:**
- Modify: `frontend/src/components/price-chart.tsx`

**Context for subagent:**
- When "Technical Panels" toggle is ON, the indicator string becomes "sma,rsi,macd" (+ "bb" if Bollinger also on).
- Create two additional panes: RSI and MACD.
- Panes are created/destroyed when the toggle changes (not just hidden — lightweight-charts doesn't support hiding panes).
- In the `useEffect` that builds the chart:
  - If `showTechnicalPanels` is true:
    - `const rsiPane = chart.addPane()` — creates pane index 1
    - `const macdPane = chart.addPane()` — creates pane index 2
    - Add RSI `LineSeries` to rsiPane with purple color
    - Add MACD `HistogramSeries` to macdPane (green/red per bar)
    - Add MACD line + signal `LineSeries` to macdPane
  - RSI reference lines (30, 70) rendered via `createSeriesMarkers` or price line on the RSI series
- The chart recreates on `showTechnicalPanels` change (it's in the useEffect dependency array).

- [ ] **Step 1: Add RSI pane**

When `showTechnicalPanels` is true, after creating the main chart:

```typescript
// RSI pane
const rsiPane = chart.addPane();
const rsiSeries = rsiPane.addSeries(LineSeries, {
  color: colors.rsi,
  lineWidth: 1,
  priceScaleId: "rsi",
  title: "RSI (14)",
});
rsiSeries.priceScale().applyOptions({
  scaleMargins: { top: 0.1, bottom: 0.1 },
  autoScale: true,
});
// Set RSI data
const rsiData = data.indicators.rsi
  ?.map((v, i) => ({
    time: data.prices[i].time.split("T")[0],
    value: v ?? undefined,
  }))
  .filter((d): d is { time: string; value: number } => d.value !== undefined)
  ?? [];
rsiSeries.setData(rsiData);

// RSI reference lines
rsiSeries.createPriceLine({ price: 70, color: colors.loss + "60", lineWidth: 1, lineStyle: 2, title: "70" });
rsiSeries.createPriceLine({ price: 30, color: colors.gain + "60", lineWidth: 1, lineStyle: 2, title: "30" });
```

- [ ] **Step 2: Add MACD pane**

```typescript
// MACD pane
const macdPane = chart.addPane();
const macdHistSeries = macdPane.addSeries(HistogramSeries, {
  priceScaleId: "macd",
  title: "MACD",
});
const macdHistData = data.indicators.macd_histogram
  ?.map((v, i) => ({
    time: data.prices[i].time.split("T")[0],
    value: v ?? 0,
    color: (v ?? 0) >= 0 ? colors.gain + "80" : colors.loss + "80",
  }))
  ?? [];
macdHistSeries.setData(macdHistData);

// MACD line + signal line
const macdLineSeries = macdPane.addSeries(LineSeries, {
  color: colors.chart1,
  lineWidth: 1,
  priceScaleId: "macd",
  title: "MACD Line",
});
const macdLineData = data.indicators.macd_line
  ?.map((v, i) => ({
    time: data.prices[i].time.split("T")[0],
    value: v ?? undefined,
  }))
  .filter((d): d is { time: string; value: number } => d.value !== undefined)
  ?? [];
macdLineSeries.setData(macdLineData);

const macdSignalSeries = macdPane.addSeries(LineSeries, {
  color: colors.chart2,
  lineWidth: 1,
  lineStyle: 2,
  priceScaleId: "macd",
  title: "Signal",
});
const macdSignalData = data.indicators.macd_signal
  ?.map((v, i) => ({
    time: data.prices[i].time.split("T")[0],
    value: v ?? undefined,
  }))
  .filter((d): d is { time: string; value: number } => d.value !== undefined)
  ?? [];
macdSignalSeries.setData(macdSignalData);

// Zero line
macdHistSeries.createPriceLine({ price: 0, color: "rgba(255,255,255,0.1)", lineWidth: 1, lineStyle: 0 });
```

- [ ] **Step 3: Add `showTechnicalPanels` to useEffect deps**

The chart `useEffect` dependency array should include `showTechnicalPanels` and `showBollinger` so the chart recreates when toggles change.

- [ ] **Step 4: Run tests and lint**

```bash
cd frontend && npx jest --no-coverage && npm run lint && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/price-chart.tsx
git commit -m "feat(chart): RSI + MACD sub-panels with Technical Panels toggle [KAN-559]"
```

---

### Task 8: Frontend — Bollinger Bands overlay

**Files:**
- Modify: `frontend/src/components/price-chart.tsx`

**Context for subagent:**
- When Bollinger toggle is ON, add "bb" to the indicator request string.
- Render Bollinger as a shaded area between upper and lower bands.
- Use two `LineSeries` (upper + lower, thin lines) + one `AreaSeries` or custom rendering.
- Actually, lightweight-charts doesn't have native area-between-two-lines. Best approach: use two `LineSeries` for upper/lower bands with semi-transparent color, and a `LineSeries` for the middle band (dashed).
- Color: blue (`chart4` or a dedicated BB CSS var).

- [ ] **Step 1: Add Bollinger overlay when toggled on**

Inside the chart creation `useEffect`, after SMA overlays:

```typescript
if (showBollinger && data.indicators.bb_upper && data.indicators.bb_lower) {
  const bbColor = "#60a5fa"; // blue-400

  const bbUpperSeries = chart.addSeries(LineSeries, {
    color: bbColor + "60",
    lineWidth: 1,
    lineStyle: 2,
    priceScaleId: "right",
  });
  const bbUpperData = data.indicators.bb_upper
    .map((v, i) => ({
      time: data.prices[i].time.split("T")[0],
      value: v ?? undefined,
    }))
    .filter((d): d is { time: string; value: number } => d.value !== undefined);
  bbUpperSeries.setData(bbUpperData);

  const bbLowerSeries = chart.addSeries(LineSeries, {
    color: bbColor + "60",
    lineWidth: 1,
    lineStyle: 2,
    priceScaleId: "right",
  });
  const bbLowerData = data.indicators.bb_lower
    .map((v, i) => ({
      time: data.prices[i].time.split("T")[0],
      value: v ?? undefined,
    }))
    .filter((d): d is { time: string; value: number } => d.value !== undefined);
  bbLowerSeries.setData(bbLowerData);

  // Middle band (SMA 20)
  if (data.indicators.bb_middle) {
    const bbMiddleSeries = chart.addSeries(LineSeries, {
      color: bbColor + "40",
      lineWidth: 1,
      lineStyle: 0,
      priceScaleId: "right",
    });
    const bbMiddleData = data.indicators.bb_middle
      .map((v, i) => ({
        time: data.prices[i].time.split("T")[0],
        value: v ?? undefined,
      }))
      .filter((d): d is { time: string; value: number } => d.value !== undefined);
    bbMiddleSeries.setData(bbMiddleData);
  }
}
```

- [ ] **Step 2: Run tests and lint**

```bash
cd frontend && npx jest --no-coverage && npm run lint
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/components/price-chart.tsx
git commit -m "feat(chart): Bollinger Bands overlay toggle [KAN-559]"
```

---

### Task 9: Frontend — Golden cross / death cross markers

**Files:**
- Modify: `frontend/src/components/price-chart.tsx`

**Context for subagent:**
- Detect crossovers from the SMA 50 and SMA 200 arrays.
- Use `createSeriesMarkers` from lightweight-charts to add circle + text annotations.
- Detection logic (client-side):
  - For each index i where both sma_50[i] and sma_200[i] are non-null:
    - If sma_50[i] > sma_200[i] AND sma_50[i-1] <= sma_200[i-1] → Golden Cross
    - If sma_50[i] < sma_200[i] AND sma_50[i-1] >= sma_200[i-1] → Death Cross
- Markers placed on the price series (candlestick or line).

- [ ] **Step 1: Add cross detection utility**

```typescript
import { createSeriesMarkers, type SeriesMarker } from "lightweight-charts";

function detectSmaCrossovers(
  sma50: (number | null)[],
  sma200: (number | null)[],
  times: string[],
): SeriesMarker<string>[] {
  const markers: SeriesMarker<string>[] = [];
  for (let i = 1; i < sma50.length; i++) {
    const prev50 = sma50[i - 1];
    const prev200 = sma200[i - 1];
    const curr50 = sma50[i];
    const curr200 = sma200[i];
    if (prev50 === null || prev200 === null || curr50 === null || curr200 === null) continue;

    if (curr50 > curr200 && prev50 <= prev200) {
      markers.push({
        time: times[i],
        position: "belowBar",
        color: "#f59e0b",
        shape: "circle",
        text: "Golden Cross",
      });
    } else if (curr50 < curr200 && prev50 >= prev200) {
      markers.push({
        time: times[i],
        position: "aboveBar",
        color: "#ef4444",
        shape: "circle",
        text: "Death Cross",
      });
    }
  }
  return markers;
}
```

- [ ] **Step 2: Apply markers after setting price data**

```typescript
// After priceSeries.setData(...)
if (data.indicators.sma_50 && data.indicators.sma_200) {
  const times = data.prices.map((p) => p.time.split("T")[0]);
  const crossMarkers = detectSmaCrossovers(data.indicators.sma_50, data.indicators.sma_200, times);
  if (crossMarkers.length > 0) {
    createSeriesMarkers(priceSeries, crossMarkers);
  }
}
```

- [ ] **Step 3: Write unit test for cross detection**

Extract `detectSmaCrossovers` to `frontend/src/lib/chart-utils.ts` and test in `frontend/src/__tests__/lib/chart-utils.test.ts`:

```typescript
import { detectSmaCrossovers } from "@/lib/chart-utils";

describe("detectSmaCrossovers", () => {
  it("detects golden cross", () => {
    const sma50 = [null, 100, 101, 103]; // crosses above sma200
    const sma200 = [null, 102, 102, 102];
    const times = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"];
    const markers = detectSmaCrossovers(sma50, sma200, times);
    expect(markers).toHaveLength(1);
    expect(markers[0].text).toBe("Golden Cross");
    expect(markers[0].time).toBe("2025-01-04");
  });

  it("detects death cross", () => {
    const sma50 = [null, 103, 102, 100]; // crosses below sma200
    const sma200 = [null, 101, 101, 101];
    const times = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"];
    const markers = detectSmaCrossovers(sma50, sma200, times);
    expect(markers).toHaveLength(1);
    expect(markers[0].text).toBe("Death Cross");
  });

  it("returns empty array when no crossovers", () => {
    const sma50 = [null, 110, 111, 112]; // always above
    const sma200 = [null, 100, 100, 100];
    const times = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"];
    const markers = detectSmaCrossovers(sma50, sma200, times);
    expect(markers).toHaveLength(0);
  });

  it("skips null values", () => {
    const sma50 = [null, null, null];
    const sma200 = [null, null, null];
    const times = ["2025-01-01", "2025-01-02", "2025-01-03"];
    const markers = detectSmaCrossovers(sma50, sma200, times);
    expect(markers).toHaveLength(0);
  });
});
```

- [ ] **Step 4: Commit**

```bash
cd frontend && git add .
git commit -m "feat(chart): golden cross / death cross markers [KAN-559]"
```

---

### Task 10: Cleanup + full test suite

**Files:**
- Delete: `frontend/src/components/signal-cards.tsx`
- Delete: `frontend/src/components/signal-history-chart.tsx`
- Modify: `frontend/src/__tests__/integration/stock-detail.test.tsx`

- [ ] **Step 1: Delete removed components**

```bash
rm frontend/src/components/signal-cards.tsx
rm frontend/src/components/signal-history-chart.tsx
```

- [ ] **Step 2: Update stock-detail integration test**

Remove the mock definitions for `SignalCards` and `SignalHistoryChart`. Update any assertions referencing "signal-cards" or "signal-history-chart" test IDs.

- [ ] **Step 3: Run full test suites**

```bash
# Backend
uv run pytest tests/unit/ -q --tb=short

# Frontend
cd frontend && npx jest --no-coverage && npx tsc --noEmit && npm run lint

# Backend lint
uv run ruff check backend/ tests/ scripts/ --fix && uv run ruff format backend/ tests/ scripts/
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove signal-cards + signal-history-chart (replaced by unified chart) [KAN-559]"
```

---

## Summary

| PR | Tasks | What ships |
|----|-------|-----------|
| **PR1** | Tasks 1-6 | Backend indicator endpoint, legend strip, chart rewrite with SMA overlays, Line/Candle both on lightweight-charts |
| **PR2** | Tasks 7-10 | RSI/MACD sub-panels, Bollinger toggle, golden/death cross markers, cleanup |
