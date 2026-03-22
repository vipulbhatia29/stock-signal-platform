# Sectors Page — Design Spec (KAN-94)

**Date:** 2026-03-22
**Status:** Draft
**Scope:** Backend endpoints + Frontend page + Dashboard cleanup

---

## 1. Overview

A dedicated `/sectors` page that provides sector-level analysis: allocation overview,
per-sector stock comparison, and price correlation heatmap. Replaces the redundant
dual-donut layout on the dashboard with a single larger allocation donut.

### Goals

- Show portfolio sector allocation at a glance
- Enable per-sector drill-down with stock comparison tables
- Surface diversification insights via correlation heatmap + table
- Clean up dashboard by removing duplicate Sector Allocation section

### Non-goals

- Sector rotation timing signals (Phase 5+)
- Cross-sector correlation (only intra-sector)
- Pre-computed/cached aggregations (on-the-fly is sufficient for personal tool scale)

---

## 2. Backend API

All endpoints require authentication. Added to existing `backend/routers/sectors.py` (new file).

### 2.1 `GET /api/v1/sectors`

Returns all sectors with aggregated stats.

**Query params:**
- `scope` — `portfolio | watchlist | all` (default: `portfolio`). Controls which stocks count as "yours."

**Response:**
```json
{
  "sectors": [
    {
      "sector": "Technology",
      "stock_count": 45,
      "avg_composite_score": 0.62,
      "avg_return_pct": 12.3,
      "your_stock_count": 4,
      "allocation_pct": 35.2
    }
  ]
}
```

**Logic:**
- Query all `Stock` rows, group by `sector`. Stocks with `sector = NULL` are grouped under `"Unknown"` (consistent with portfolio router convention).
- For each sector, compute: count, avg composite_score (from latest `SignalSnapshot`), avg return_pct (use `SignalSnapshot.annual_return` where available — no extra price query needed).
- `your_stock_count`: count of stocks in user's portfolio/watchlist/both depending on scope.
- `allocation_pct`: portfolio `market_value` in that sector / total portfolio value × 100. `market_value` is derived as `position.shares × latest StockPrice.adj_close` (requires join: `Position` → `Stock.sector` + subquery on `StockPrice` for latest close per ticker). Only meaningful for portfolio scope; `0.0` for watchlist-only.
- Sort by `allocation_pct` descending (portfolio-weighted sectors first).
- Expected cardinality: ~11 GICS sectors — no pagination needed.

**Pydantic schema:** `SectorSummaryResponse`

### 2.2 `GET /api/v1/sectors/{sector}/stocks`

Returns stocks in a given sector with metrics and user ownership flags.

**URL encoding:** The `{sector}` path parameter is a URL-encoded sector name (e.g., `Consumer%20Defensive`, `Real%20Estate`). The frontend must use `encodeURIComponent(sector)` when constructing URLs. The backend decodes automatically via FastAPI's path parameter handling.

**Response:**
```json
{
  "sector": "Technology",
  "stocks": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "composite_score": 0.72,
      "current_price": 185.50,
      "return_pct": 15.2,
      "is_held": true,
      "is_watched": true
    }
  ]
}
```

**Logic:**
- Return top 20 stocks by composite_score in the given sector.
- Always include all user's portfolio + watchlist stocks in that sector, even if outside top 20.
- `is_held`: stock exists in user's portfolio positions.
- `is_watched`: stock exists in user's watchlist.
- `return_pct`: use `SignalSnapshot.annual_return` where available. Fallback: compute from latest vs 30-trading-day-ago `StockPrice.adj_close`. If insufficient price data, return `null`.
- Sort: user's stocks first (held > watched > neither), then by composite_score descending.

**Pydantic schema:** `SectorStocksResponse`

### 2.3 `GET /api/v1/sectors/{sector}/correlation`

Computes Pearson correlation on **daily returns** (not raw prices) for selected stocks in a sector.

**URL encoding:** Same as 2.2 — `{sector}` is URL-encoded.

**Query params:**
- `tickers` — comma-separated list (e.g., `AAPL,MSFT,GOOGL`). If omitted, uses user's portfolio+watchlist stocks in that sector.
- `period_days` — integer, default `90`.

**Response:**
```json
{
  "sector": "Technology",
  "tickers": ["AAPL", "MSFT", "GOOGL", "NVDA"],
  "matrix": [
    [1.0, 0.85, 0.72, 0.68],
    [0.85, 1.0, 0.79, 0.74],
    [0.72, 0.79, 1.0, 0.65],
    [0.68, 0.74, 0.65, 1.0]
  ],
  "period_days": 90,
  "excluded_tickers": [
    {"ticker": "XYZ", "reason": "insufficient price data (12 points)"}
  ]
}
```

**Pydantic schema:** `CorrelationResponse`

**Logic:**
- Fetch `adj_close` from `StockPrice` for the given tickers over `period_days`.
- Compute daily returns via `pandas.DataFrame.pct_change()`, then Pearson correlation via `.corr()`.
- Cap at 15 tickers max — return 400 if exceeded.
- Stocks with insufficient price data (<30 data points) are excluded and listed in `excluded_tickers`.
- Matrix is symmetric; `matrix[i][j]` = correlation between `tickers[i]` and `tickers[j]`.

**Error cases:**
- Sector not found → 404
- < 2 tickers with sufficient data → 400 with message
- Tickers not in sector → 400

---

## 3. Frontend — Sectors Page

### 3.1 Page Structure (`/sectors`)

```
┌─────────────────────────────────────────────────┐
│ Sectors                    [Portfolio ▾ | Watchlist | All] │
├─────────────────────────────────────────────────┤
│ ┌─────────────┐                                 │
│ │  Allocation  │  (Large donut — portfolio only, │
│ │    Donut     │   hidden when scope=watchlist)  │
│ └─────────────┘                                 │
├─────────────────────────────────────────────────┤
│ ▸ Technology    45 stocks  Avg 0.62  +12.3%  4 yours  35.2% │
│ ▾ Healthcare    32 stocks  Avg 0.55  +8.1%   2 yours  22.1% │
│   ┌─────────────────────────────────────────┐   │
│   │ Your Stocks (2)                         │   │
│   │  JNJ  0.68  $162.30  +5.2%  Held        │   │
│   │  PFE  0.45  $28.50   -3.1%  Watched     │   │
│   ├─────────────────────────────────────────┤   │
│   │ Top Sector Stocks (20)                  │   │
│   │  UNH  0.78  $512.40  +18.3%  —          │   │
│   │  LLY  0.75  $780.20  +22.1%  —          │   │
│   │  ...                                    │   │
│   ├─────────────────────────────────────────┤   │
│   │ Correlation   [Heatmap ▪ | Table ▪]     │   │
│   │  ┌────┬────┬────┐                       │   │
│   │  │    │JNJ │PFE │  (heatmap view)       │   │
│   │  │JNJ │1.00│0.42│                       │   │
│   │  │PFE │0.42│1.00│                       │   │
│   │  └────┴────┴────┘                       │   │
│   └─────────────────────────────────────────┘   │
│ ▸ Financials    28 stocks  Avg 0.51  +6.7%   1 yours  18.4% │
│ ▸ ...                                           │
└─────────────────────────────────────────────────┘
```

### 3.2 Scope Toggle Behavior

| Scope | Donut | "Your Stocks" shows | Correlation default tickers |
|-------|-------|--------------------|-----------------------------|
| Portfolio | Visible (portfolio allocation) | Held stocks only | Held stocks in sector |
| Watchlist | Hidden | Watched stocks only | Watched stocks in sector |
| All | Visible (portfolio allocation) | Held + Watched (deduplicated) | Held + Watched in sector |

### 3.3 Correlation Interaction

- **Default:** When accordion expands, correlation loads with user's stocks in that sector.
- **Add stock:** Click a stock in "Top Sector Stocks" table → adds to correlation tickers, re-fetches.
- **Remove stock:** Click ✕ on a ticker chip above the heatmap → removes, re-fetches.
- **Max 15 tickers** — disable add button when at cap.
- **Heatmap colors:** green (#22c55e, <0.3) → yellow (#eab308, 0.3-0.7) → red (#ef4444, >0.7). Diagonal is always 1.0 (neutral gray).
- **Table view:** Ranked pairs: "AAPL ↔ MSFT: 0.85 (Highly correlated)", sorted by correlation descending.

### 3.4 New Components

| Component | Purpose |
|-----------|---------|
| `SectorAccordion` | Collapsible card: collapsed shows stats, expanded shows 3 sections |
| `SectorStocksTable` | Comparison table with score, price, return, Held/Watched badges |
| `CorrelationHeatmap` | Color-coded grid, custom SVG or div-based (not Recharts) |
| `CorrelationTable` | Ranked pairs list with interpretation text |
| `CorrelationTickerChips` | Selected tickers as removable chips above heatmap |

### 3.5 Reused Components

`AllocationDonut`, `ScoreBar`, `ChangeIndicator`, `SectionHeading`, `PageTransition`,
`StaggerGroup`, `StaggerItem`, `ScoreBadge`, `SignalBadge`

---

## 4. Dashboard Cleanup

### 4.1 Remove Sector Allocation Section

- Remove the `grid-cols-3` split between "Action Required" and "Sector Allocation"
- "Action Required" section gets full width (`grid-cols-1`)
- Delete the `<Link href="/sectors">` donut card

### 4.2 Bigger Allocation StatTile

- The "Allocation" StatTile in the KPI row stays — it's portfolio allocation
- Increase donut size within the tile: larger `AllocationDonut` render (taller tile or bigger radius)
- On click → navigate to `/sectors`

---

## 5. Data Flow

```
User lands on /sectors
  → GET /api/v1/sectors?scope=portfolio
  → Render sector cards (collapsed)

User expands "Technology"
  → GET /api/v1/sectors/Technology/stocks
  → GET /api/v1/sectors/Technology/correlation (auto with user's tickers)
  → Render Your Stocks + Top Stocks table + Heatmap

User clicks "UNH" in Top Stocks table
  → Re-fetch GET /api/v1/sectors/Technology/correlation?tickers=AAPL,MSFT,UNH
  → Heatmap updates with new stock

User switches scope to "Watchlist"
  → Re-fetch GET /api/v1/sectors?scope=watchlist
  → Donut hides
  → Expanded sector (if any) re-fetches stocks + correlation
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| No stocks in sector for user | "You don't have any stocks in this sector" + show Top Stocks table |
| < 2 stocks for correlation | "Add at least 2 stocks to see correlation" message |
| Price data missing for a ticker | Exclude from correlation, show warning chip |
| Sector endpoint fails | ErrorState component with retry |
| Empty portfolio | Donut hidden, message: "Add positions to see allocation" |
| Stock has no sector data | Group under "Unknown" sector (consistent with portfolio router convention) |
| Ticker excluded from correlation | Show warning chip: "XYZ excluded — insufficient data" |

---

## 7. Testing

### Backend
- Unit tests for correlation computation (known values)
- Unit tests for sector aggregation logic
- API tests for all 3 endpoints (auth, happy path, edge cases)
- Edge: sector with 1 stock, sector with no price data, invalid sector name

### Frontend
- Component tests for SectorAccordion (collapse/expand)
- Component tests for CorrelationHeatmap (color mapping)
- Integration: scope toggle re-fetches data
- Snapshot: empty state rendering

---

## 8. File Inventory

### New files
- `backend/routers/sectors.py` — 3 endpoints
- `frontend/src/app/(authenticated)/sectors/page.tsx` — page wrapper
- `frontend/src/app/(authenticated)/sectors/sectors-client.tsx` — client component
- `frontend/src/components/sector-accordion.tsx`
- `frontend/src/components/sector-stocks-table.tsx`
- `frontend/src/components/correlation-heatmap.tsx`
- `frontend/src/components/correlation-table.tsx`
- `frontend/src/components/correlation-ticker-chips.tsx`
- `frontend/src/hooks/use-sectors.ts` — TanStack Query hooks

### Modified files
- `backend/main.py` — register sectors router
- `frontend/src/app/(authenticated)/dashboard/page.tsx` — remove Sector Allocation section, bigger donut
- `frontend/src/components/allocation-donut.tsx` — add size prop for larger rendering
- `frontend/src/types/api.ts` — add sector response types
