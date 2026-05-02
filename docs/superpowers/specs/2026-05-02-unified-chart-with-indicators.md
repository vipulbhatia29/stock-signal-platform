# Unified Chart with Indicator Overlays & Sub-Panels

**Date:** 2026-05-02
**Status:** Draft
**Author:** PM + Claude (Session 148 brainstorm)

---

## 1. Problem

The stock detail price chart is disconnected from its indicators. SMA 50/200 values appear as numbers in cards ("50: 261, 200: 255") instead of lines overlaid on the price chart — users can't see golden crosses, death crosses, or price-relative-to-SMA visually. RSI and MACD are static cards showing only the latest value with no trend history. The Recharts line chart lacks zoom, pan, and crosshair. Competitor platforms (TradingView, the SBIN.NS dashboard the PM compared against) show all of this in a single interactive chart.

## 2. Solution

Replace the current price section (Recharts line chart + 4 Signal Breakdown cards + Signal History chart) with a unified lightweight-charts instance that includes:

- **SMA 50/200 overlays** (always on) drawn on the price chart
- **Bollinger Bands overlay** (toggleable, off by default) — shaded fill between upper and lower bands
- **RSI sub-panel** (toggleable via "Technical Panels" toggle, off by default)
- **MACD sub-panel** (toggleable via "Technical Panels" toggle, off by default)
- **Compact legend strip** (always visible) — pill-shaped badges showing current value + plain-English label for each indicator
- **Volume bars** (always on) below the price chart

The Recharts line chart is removed entirely — lightweight-charts handles both Line and Candle modes with native zoom, pan, and crosshair.

## 3. Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chart library for price | lightweight-charts v5 only | Already installed, TradingView-quality rendering, native zoom/pan/crosshair. Kill Recharts for price section. |
| SMA visibility | Always on | Core value — golden cross / death cross must be immediately visible |
| Bollinger visibility | Toggle (off by default) | Adds visual clutter when not needed; toggle keeps chart clean |
| RSI + MACD | Single "Technical Panels" toggle | Keep it simple — one toggle shows both sub-panels together |
| Signal Breakdown cards | Replaced by legend strip | Pill badges are more compact, always visible, preserve plain-English interpretations |
| Signal History chart | Removed | Replaced by the RSI sub-panel (which shows RSI history at any zoom level, not just 90 days) |
| Line mode | lightweight-charts line series | Replaces Recharts line chart — same zoom/pan/crosshair as candle mode |
| Backend indicator data | New query param on existing endpoint | `/stocks/{ticker}/prices?indicators=sma,bb,rsi,macd` returns aligned time series |

## 4. UI Layout

### 4.1 Toolbar Row

```
[Line] [Candle]  |  [1M] [3M] [6M] [1Y] [5Y]              [Bollinger] [Technical Panels]
```

- Left: chart mode toggle (Line / Candle) + period selector (1M/3M/6M/1Y/5Y)
- Right: indicator toggles (Bollinger, Technical Panels)
- Active toggles use the existing accent color with border highlight

### 4.2 Legend Strip

Always visible row of pill badges below the toolbar:

```
[RSI 66.4 Neutral] [MACD 0.91 Bullish] [SMA Above 200 —50 —200] [BB 253–280 Upper] [ADX 28.3 Trending] [Gate Score 7.5 WATCH]
```

- Each pill has a subtle colored border matching its indicator color
- Plain-English label (Neutral, Bullish, Above 200, Upper, Trending, WATCH) in indicator color
- SMA pill includes tiny colored line segments as a legend key for the overlay colors
- Gate Score pill shows the confirmation-gate composite score + recommendation label
- Data source: existing `/stocks/{ticker}/signals` endpoint (same as current cards)

### 4.3 Main Chart

- **Candlestick / Line series** — full price data from `/stocks/{ticker}/prices`
- **SMA 50 overlay** — solid orange line (`--chart-sma-50` CSS variable)
- **SMA 200 overlay** — dashed red line (`--chart-sma-200` CSS variable)
- **Bollinger Bands** (when toggled on) — shaded fill between upper and lower bands with middle line
- **Golden Cross / Death Cross markers** — circle annotation where SMA 50 crosses SMA 200, with label. Computed client-side from the SMA series data.
- **Volume bars** — below the price chart, colored green/red based on close vs previous close
- **Interactions:** mouse-wheel zoom, drag-to-pan, crosshair with price/time readout

### 4.4 Technical Sub-Panels (when toggled on)

Appear below the volume bars. Each panel is a separate lightweight-charts pane synchronized with the main chart's time scale.

**RSI Panel (~60px height):**
- RSI line (purple, `--chart-rsi` CSS variable)
- Horizontal reference lines at 70 (overbought, red dashed) and 30 (oversold, green dashed)
- Current value label on right edge
- Shared crosshair with main chart

**MACD Panel (~60px height):**
- MACD histogram bars (green above zero, red below zero)
- MACD line + signal line
- Zero reference line
- Current histogram + line values on right edge
- Shared crosshair with main chart

## 5. Backend: Indicator Series Endpoint

### 5.1 API Change

New dedicated endpoint (avoids breaking the existing `format=list` / `format=ohlc` response shapes):

```
GET /api/v1/stocks/{ticker}/prices/with-indicators?period=1y&indicators=sma,bb,rsi,macd
```

**`indicators` values:** `sma`, `bb`, `rsi`, `macd` (comma-separated, at least one required)

The existing `/stocks/{ticker}/prices` endpoint remains unchanged — no breaking changes for other consumers (though currently only the stock detail page uses it).

### 5.2 Response Shape

```json
{
  "prices": [
    {"time": "2025-05-01", "open": 250.0, "high": 255.0, "low": 248.0, "close": 253.0, "volume": 45000000},
    ...
  ],
  "indicators": {
    "sma_50": [null, null, ..., 261.2, 261.5],
    "sma_200": [null, null, ..., 255.1, 255.3],
    "bb_upper": [null, ..., 280.1],
    "bb_lower": [null, ..., 253.2],
    "bb_middle": [null, ..., 266.5],
    "rsi": [null, ..., 66.4],
    "macd_histogram": [null, ..., 0.91],
    "macd_line": [null, ..., 4.36],
    "macd_signal": [null, ..., 3.45]
  }
}
```

- Each indicator array is the same length as `prices`, aligned by index
- NaN warmup values serialized as `null`
- Only requested indicators are included in the response
- Computation uses the existing `pandas-ta` functions from `backend/services/signals.py` and `backend/services/feature_engineering.py`

### 5.3 Backend Implementation

- New endpoint handler in `backend/routers/stocks/data.py` — reuses the existing price-loading logic
- Parse `indicators` query param, compute requested series from the OHLCV DataFrame using pandas-ta
- Reuse existing constants from `backend/services/signals.py`: `RSI_PERIOD=14`, `MACD_FAST=12`, `MACD_SLOW=26`, `MACD_SIGNAL=9`, `SMA_SHORT=50`, `SMA_LONG=200`, `BB_PERIOD=20`, `BB_STD_DEV=2`
- New response schema: `PriceWithIndicatorsResponse` (prices array + indicators dict)
- Existing `/stocks/{ticker}/prices` endpoint unchanged (no breaking change)

## 6. Frontend Implementation

### 6.1 Files Changed

| File | Change |
|------|--------|
| `components/price-chart.tsx` | Rewrite — single lightweight-charts instance for both Line and Candle. Add overlay series for SMA/BB. Add sub-panes for RSI/MACD. Remove Recharts imports. |
| `components/candlestick-chart.tsx` | Absorb into `price-chart.tsx` or extend to handle line mode + overlays |
| `components/signal-cards.tsx` | Remove (replaced by legend strip) |
| `components/signal-history-chart.tsx` | Remove (replaced by RSI sub-panel) |
| `components/indicator-legend-strip.tsx` | New — pill badges row |
| `hooks/use-stocks.ts` | Add `usePricesWithIndicators` hook for new endpoint. Keep `usePrices` for other consumers. |
| `app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx` | Remove SignalCards + SignalHistoryChart sections, add legend strip |
| `lib/lightweight-chart-theme.ts` | Add indicator color configs |
| `types/api.ts` | Add `PriceWithIndicatorsResponse`, indicator types |

### 6.2 lightweight-charts Architecture

lightweight-charts v5 supports multiple panes in a single chart via `chart.addPane()`. Panes must be created before series are added to them via `paneIndex`. The architecture:

```
// Creation order matters:
const chart = createChart(container);
// Main pane is implicit (paneIndex 0)
const rsiPane = chart.addPane();   // paneIndex 1
const macdPane = chart.addPane();  // paneIndex 2

chart (single instance)
├── Main pane (index 0)
│   ├── Candlestick/Line series (price)
│   ├── Line series (SMA 50, orange)
│   ├── Line series (SMA 200, red dashed)
│   ├── Area series (Bollinger upper/lower fill) — toggleable
│   ├── Histogram series (volume)
│   └── Markers (golden cross / death cross annotations)
├── RSI pane (index 1, toggleable — created/destroyed on toggle)
│   ├── Line series (RSI value, purple)
│   └── Horizontal lines (30, 70)
└── MACD pane (index 2, toggleable — created/destroyed on toggle)
    ├── Histogram series (MACD histogram, green/red)
    ├── Line series (MACD line)
    └── Line series (Signal line)
```

All panes share the same time scale — zoom/pan/crosshair syncs automatically.

### 6.3 Golden Cross / Death Cross Detection

Client-side detection from SMA series data:

```
For each index i where both sma_50[i] and sma_200[i] are non-null:
  If sma_50[i] > sma_200[i] AND sma_50[i-1] <= sma_200[i-1]:
    → Golden Cross marker at prices[i].time
  If sma_50[i] < sma_200[i] AND sma_50[i-1] >= sma_200[i-1]:
    → Death Cross marker at prices[i].time
```

Rendered as lightweight-charts markers (circle + label text).

## 7. What Gets Removed

| Component | Reason |
|-----------|--------|
| `SignalCards` (4 full-width cards) | Replaced by compact legend strip — same data, less vertical space |
| `SignalHistoryChart` (Recharts 90-day) | RSI sub-panel now shows RSI at any zoom level, not just fixed 90 days |
| Recharts `ComposedChart` in `price-chart.tsx` | Replaced by lightweight-charts line series (zoom/pan/crosshair) |
| `useOHLC` + `usePrices` in price-chart | Replaced by single `usePricesWithIndicators` hook calling new endpoint |

## 8. What Does NOT Change

- **Signal Convergence section** — stays as-is (STRONG BULL badge, signal arrows, rationale)
- **Benchmark Comparison chart** — stays as Recharts (different purpose, not price analysis)
- **Risk & Returns, Fundamentals, Forecast, Intelligence, Sentiment, News, Dividends** — all unchanged
- **Screener, Dashboard, Portfolio pages** — no changes
- **Signal computation backend** — no changes to how signals are computed or stored
- **Recharts dependency** — stays for Benchmark, Signal History on other pages, etc. Just removed from the price section.

## 9. Testing

### 9.1 Backend
- Unit test: indicator computation returns correct array lengths aligned with prices
- Unit test: `indicators` param parsing (empty, single, multiple, invalid)
- Unit test: null values for warmup period
- API test: endpoint returns indicators when requested, omits when not

### 9.2 Frontend
- Jest: `IndicatorLegendStrip` renders all pills with correct values and labels
- Jest: toggle state management (Bollinger, Technical Panels)
- Jest: golden cross / death cross detection logic
- Playwright: visual regression — chart renders with SMA overlays visible
- Playwright: zoom interaction (mouse wheel changes visible date range)

## 10. Estimated Scope

| Task | Effort |
|------|--------|
| Backend: indicator series computation + endpoint extension | 0.5 day |
| Frontend: rewrite price-chart.tsx with lightweight-charts overlays | 1.5 days |
| Frontend: RSI + MACD sub-panels | 1 day |
| Frontend: legend strip component | 0.5 day |
| Frontend: toggle state + wiring | 0.5 day |
| Tests (backend + frontend) | 1 day |
| **Total** | **~5 days** |

Split into 2 PRs:
- **PR1:** Backend indicator endpoint + frontend chart rewrite with SMA overlays + legend strip
- **PR2:** RSI/MACD sub-panels + Bollinger toggle + golden cross markers + tests
