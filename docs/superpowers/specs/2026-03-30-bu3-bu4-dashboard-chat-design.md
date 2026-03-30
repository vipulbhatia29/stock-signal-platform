# BU-3 Dashboard Redesign + BU-4 Chat Cleanup — Design Spec

**Date:** 2026-03-30
**JIRA:** KAN-229 (BU-3), KAN-230 (BU-4)
**Epic:** KAN-226 (Phase B.5 Frontend Catch-Up)
**Visual Reference:** `docs/mockups/dashboard-bulletin-v3.html` — open in browser, this is the approved layout

---

## 1. Overview

The dashboard is redesigned from a mixed KPI/watchlist page into a **Daily Intelligence Briefing** — a 5-zone bulletin board that a passive investor scans top-to-bottom in 2 minutes to answer: what's happening in the market, what should I buy, what should I dump, and how is my portfolio positioned.

The chat system (BU-4) gets a scoped cleanup: tools list update, feedback persistence, type sync. No observability data in chat — that belongs on the observability page.

## 2. Design Principles

- **Bulletin board, not dashboard:** Information flows top-to-bottom in priority order. No tabs, no toggles on the main page.
- **2-minute scan:** A passive investor checking weekly should be able to read Zones 1-3 and know what to do.
- **Green/Orange/Red system:** Green glow = doing well, orange = needs watching, red = needs action. Applied consistently to borders, score rings, metric values, alert severity dots. **All color indicators must have a text or shape alternative** (action badges, severity labels, directional arrows) for colorblind users (~8% of males).
- **Every stock shows metrics:** Price, Change%, MACD signal, RSI minimum. Context-appropriate extras: P/E, Piotroski, FCF Yield, SMA crossover, Insider activity. **Primary metrics (Price, Chg%) are visually prominent; technical metrics (MACD, RSI, P/E) are secondary cluster** with jargon tooltips (e.g., "Piotroski 8/9" → hover: "Financial strength score 0-9. 8+ is excellent").
- **Glassmorphism:** Cards use `backdrop-filter: blur(16px)`, subtle top highlight gradient, navy-900 background. Matches existing design system tokens.
- **Independent zone loading:** Each zone renders independently — loading skeleton → data → error card with retry. A failed zone never blanks the whole page. Partial failures show dashes ("—") for missing values.
- **Market session awareness:** Market Pulse label shows session status: green pulsing "LIVE" dot during market hours, gray dot + "Market Closed — As of [date] 4:00 PM ET" outside hours.
- **Minimum font sizes:** 11px for labels, 12px for values. No 9-10px text (target demographic: 35-55 age range).
- **Keyboard navigation:** All clickable elements (stock cards, alert tiles, news cards, sector bars) have `:focus-visible` ring styles.

## 3. Dashboard Layout — 5 Zones

### Zone 1: Market Pulse
**Purpose:** "What's the market doing?" — answered in one glance.

**Layout:** Glass card, 2-column grid.
- **Left:** 3 index chips (S&P 500, NASDAQ, DOW 30). Each chip: name, value, change%. Green/red left border based on direction.
- **Right:** 4 top movers in 2×2 grid. Each mover row: ticker, price, MACD direction pill (↑ bullish / ↓ bearish), change%. Green/red left border.

**Data sources:**
- `useIndexes()` → `GET /indexes` (existing)
- `useMarketBriefing()` → `GET /market/briefing` (new hook) — for top_movers

**Components:**
- `IndexChip` — existing, may need minor restyling
- `MoverRow` — new component with Price + MACD pill

### Zone 2: Signals (Split)
**Purpose:** "What should I buy? What should I dump?" — the core value proposition.

**Layout:** 2-column grid of glass cards.
- **Left card — "Opportunities":** Top 3 stocks with BUY signal (score ≥ 8). Green dot in section label. Green-bordered stock cards.
- **Right card — "Action Required":** Top stocks with SELL/WATCH signals from portfolio holdings. Red dot in section label. Red-bordered (sell) or orange-bordered (watch) stock cards. **Zone 2b IS the primary alert surface for portfolio-holding alerts.** If a stock has a critical divestment alert, the alert message appears as the reason text on the card. Zone 4 is a supplementary log of all alerts (including non-portfolio alerts like earnings reminders).

**Stock card anatomy:**
```
┌─────────────────────────────────────────────────┐
│ [Score Ring 9.2]  MSFT                [Strong Buy] │
│                   Microsoft Corp                    │
│ Price $428.50 │ Chg +2.1% │ ●MACD Bullish ×over   │
│ RSI 34 │ P/E 31.2 │ Piotroski 8/9                  │
│ RSI oversold reversal + strong fundamentals + ...   │
└─────────────────────────────────────────────────┘
```

- **Score ring:** Circle with composite score. Color: green (≥8), orange (≥5), red (<5).
- **Metrics strip:** Horizontal row of metric chips. Each chip: label + value, colored by sentiment.
- **Reason text:** 1-line summary of why this signal fired. Composed on the frontend from signal data (e.g., MACD state + RSI level + fundamental highlights). Uses a `buildSignalReason(signals, fundamentals)` helper that concatenates the top 2-3 contributing factors. Not a backend field — no API change needed.
- **Action badge:** "Strong Buy", "Buy", "Watch", "Sell" — colored by category.

**Minimum metrics per stock card:** Price, Change%, MACD signal, RSI.
**Context-appropriate extras (pick 2):** P/E, Piotroski, FCF Yield, SMA crossover status, Insider activity, Dividend yield.
**Metrics visual hierarchy:** Price + Chg% on the left (slightly larger font), then a subtle divider `|`, then MACD/RSI/extras in a secondary cluster. This gives non-technical users a quick-scan path (price movement) while keeping technical metrics available for power users.
**Metric chip text alternatives:** RSI values include context: "RSI 34 (oversold)" not just "RSI 34". MACD includes directional text: "Bullish ×over" not just a colored dot.
**Mobile:** Max 4 chips per card (Price, Chg%, MACD, RSI). Drop Layer 3 fundamentals on screens < 768px.

**Data sources:**
- `useRecommendations()` → `GET /stocks/recommendations` (existing) — for opportunities
- `usePositions()` → `GET /portfolio/positions` (existing) — for action required (stocks with alerts)
- Bulk signals data for metric values

**Components:**
- `SignalStockCard` — new component (replaces old watchlist card pattern)
- `MetricsStrip` — new reusable component for metric chip rows
- `ScoreRing` — new component (circular score indicator)
- `ActionBadge` — new component (styled pill badge)

### Zone 3: Portfolio Position
**Purpose:** "How am I positioned? How am I doing?" — portfolio health at a glance.

**Layout:** Glass card with two sub-sections.

**Sub-section A — KPI Tiles Row:**
5-column grid of compact tiles above the donut. Each tile: label, primary value, contextual sub-text, bottom accent line (green/cyan).

| Tile | Source Endpoint | Primary Value | Sub-text |
|------|----------------|---------------|----------|
| Portfolio Health | `GET /portfolio/health` | Grade badge (B+) + score (7.8/10) | Weekly trend (↑ 0.3 this week) |
| Unrealized P&L | `GET /portfolio/summary` | Dollar P&L (+$8,240) | Percentage (+6.9% all time) |
| 90-Day Forecast | `GET /forecasts/portfolio` | Expected return (+4.2%) | Confidence range (+1.8% to +6.1%) |
| Signal Accuracy | `GET /recommendations/scorecard` | Hit rate (73%) | Total tracked (142 recommendations) |
| Risk-Adjusted Return | `GET /portfolio/health` metrics | Sharpe ratio (1.34) | Context ("Above market avg 1.0") |

**Sub-section B — Sector Allocation:**
2-column layout: donut chart (left, 240px) + sector performance bars (right, fluid).

- **Donut:** Sector allocation with total value + position count in center. Uses existing `AllocationDonut` (may need restyling).
- **Sector bars:** Each row: sector name, horizontal bar (green/orange/red fill), return%, score. Clickable → navigates to sectors page.

**New hooks:**
- `usePortfolioHealth()` → `GET /portfolio/health` — returns health_score, grade, components, metrics (weighted_sharpe), top_concerns, top_strengths
- Existing: `usePortfolioSummary()`, `usePortfolioForecast()`, `useScorecard()`, `usePositions()`

**Components:**
- `PortfolioKPITile` — new component (glass tile with accent line)
- `HealthGradeBadge` — new component (letter grade in colored rounded square)
- `SectorPerformanceBars` — new component (replaces or complements existing sector display)

### Zone 4: Alerts
**Purpose:** Persistent awareness of things that need attention.

**Layout:** Glass card with 3-column grid of alert tiles. No horizontal scroll.

Each alert tile:
- Severity dot: critical (pulsing red), warning (orange), info (cyan)
- Bold ticker + description text
- Timestamp (relative: "2h ago")

**Data source:** Existing alerts system (`GET /alerts` or derived from positions/signals)

**Component:** `AlertTile` — new component (replaces horizontal scroll `AlertChip`)

### Zone 5: News
**Purpose:** Market context that connects to the stocks and sectors shown above.

**Layout:** Glass card with 3-column grid of news cards.

Each news card:
- **Tag row:** Sentiment tag (Bullish green / Bearish red / Neutral gray) + ticker tag (cyan) + sector tag (purple)
- **Headline:** 1-2 line title
- **Meta:** Source name + relative time

News should be **contextual** — prioritize articles about stocks that appear in Zones 2-3 (opportunities, action required, portfolio holdings).

**Data source:** `useMarketBriefing()` → `GET /market/briefing` (portfolio_news field) + per-ticker news from existing `useStockNews()`

**Component:** `NewsCard` — already exists from BU-2, may need tag restyling

## 4. Components Removed from Dashboard

| Component | Current Location | New Location |
|-----------|-----------------|--------------|
| `WelcomeBanner` | Dashboard top | Remove (or first-login-only modal — deferred) |
| `TrendingStocks` | Dashboard below banner | Removed — Opportunities zone replaces this |
| Watchlist grid | Dashboard bottom | **Screener page** as tab toggle |

## 5. Watchlist Relocation

**Current:** 4-column card grid on dashboard bottom.
**New:** Tab on the Screener page.

**Screener page changes:**
- Add tab toggle at top: `Screener | Watchlist`
- Screener tab: existing screener functionality (unchanged)
- Watchlist tab: tracked stocks displayed with the same `SignalStockCard` format used in Zone 2 (score ring, metrics strip, reason text)
- Add/remove from watchlist actions remain the same

This keeps the dashboard as a pure bulletin board and puts the watchlist in the "stock discovery" mental space alongside the screener.

**Discoverability:** On first visit after migration, show a one-time toast: "Your watchlist moved to the Screener page. [Go to Screener]" (dismiss permanently on click, store in localStorage). The Screener tab shows a badge count: "Watchlist (8)" so users know there's content in the tab.

## 6. Chat Panel (coexists with bulletin board)

The collapsible chat sidebar already exists. It sits alongside the bulletin board. When open, the dashboard grid adapts (5→3 columns in KPI row, etc.).

**Chat = pure business.** No token counts, no cost, no trace links. All observability metadata lives on the dedicated observability page.

## 7. BU-4: Chat System Improvements (Scoped)

| Change | Detail |
|--------|--------|
| **PINNABLE_TOOLS update** | `artifact-bar.tsx` hardcodes 7 tools — update to reflect current 24 internal tools. Use dynamic list from backend if possible, otherwise update hardcoded list. |
| **Feedback visual state** | After clicking thumbs up/down, persist the selected state visually (dim unselected button, highlight selected). Backend already stores feedback. |
| **ChatMessage type sync** | Add missing fields to TS `ChatMessage` type: `prompt_tokens`, `completion_tokens`, `latency_ms`, `feedback`, `trace_id`. These fields are NOT displayed in chat — they exist for the observability page to consume. |
| **Removed from scope** | Cost-per-response in chat, Langfuse trace links in chat, token count display in chat. All of this belongs on the observability page (BU-5/6). |

## 8. New Hooks Summary

| Hook | Endpoint | Params | Notes |
|------|----------|--------|-------|
| `useMarketBriefing()` | `GET /market/briefing` | none | Global cache. Returns indexes, sectors, movers, general news, earnings. `staleTime: 5min`. |
| `usePortfolioHealth()` | `GET /portfolio/health` | none | Returns health_score, grade, 5 components, metrics dict (weighted_sharpe), concerns, strengths. |
| `usePortfolioHealthHistory(days)` | `GET /portfolio/health/history?days=N` | days (default 7) | For weekly trend computation on Health KPI tile. Returns ~7 snapshots. |
| `useUserDashboardNews(tickers)` | `GET /news/dashboard` | none (backend reads user context) | Per-user cache. Fires after recommendations resolve. Returns portfolio + recommendation news. |
| `useSectorForecast(sector)` | `GET /forecasts/sector/{sector}` | sector name | For sectors page enhancement (not dashboard). `enabled` when accordion open. |

Existing hooks reused: `useRecommendations`, `usePortfolioSummary`, `usePositions`, `usePortfolioForecast`, `useScorecard`, `useBulkSignals` (with new `tickers` param), `useFundamentals`, `useAlerts`, `useSectors`.

**Note:** `useIndexes()` is no longer used on the dashboard. Index data comes from `useMarketBriefing().indexes` which includes `price` and `change_pct` (the indexes endpoint only returns name/slug/stockCount).

## 9. Visual System Reference

All styling follows the approved mockup: `docs/mockups/dashboard-bulletin-v3.html`

**Key CSS tokens:**
- Background: `--navy-900: #0a0e1a`
- Glass card: `rgba(30, 41, 59, 0.6)` + `backdrop-filter: blur(16px)` + `border: 1px solid rgba(148, 163, 184, 0.12)`
- Green glow: `0 0 12px rgba(74, 222, 128, 0.3)` — applied on hover for buy cards
- Orange glow: `0 0 12px rgba(251, 146, 39, 0.3)` — applied on hover for watch cards
- Red glow: `0 0 12px rgba(248, 113, 113, 0.3)` — applied on hover for sell cards
- Score ring colors: green (≥8), orange (≥5), red (<5)
- Metric chip: `rgba(15, 23, 42, 0.6)` background, 6px border-radius
- Alert severity: critical = pulsing red animation, warning = orange, info = cyan
- News sentiment tags: bullish = green bg, bearish = red bg, neutral = gray bg
- KPI tile: bottom 2px accent line (green or cyan gradient)

## 10. Responsive Behavior

- **With chat panel open:** KPI row adapts 5→3 columns, signals zone stacks vertically, news/alerts go 3→2 columns
- **Mobile (< 768px):** All zones stack single-column. KPI tiles 2×2 grid (Sharpe tile hidden behind "More metrics" expand). Sector bars full-width below donut. Movers stack vertically.
- **Mobile scroll compression:** Cap visible cards per zone on mobile: 2 Opportunity + 2 Action Required cards, 3 alert tiles, 3 news cards. Each capped zone shows a "See all (N)" text link below the last visible card. Behavior: **inline expand** — clicking "See all" renders the remaining cards in place (no page navigation). Uses a `showAll` state toggle per zone. This keeps context and avoids routing complexity.
- **Mobile metric chips:** Max 4 chips per stock card (Price, Chg%, MACD, RSI). Drop P/E/Piotroski on small screens.
- Donut and sector bars maintain their relative layout until mobile breakpoint

## 10a. Empty States

Every zone must handle zero-data scenarios gracefully. No blank sections — always show a CTA or informational message. Empty states use the existing `EmptyState` component pattern (icon + heading + subtext + optional CTA button).

### Zone 1: Market Pulse — Market Closed
**Condition:** Outside US market hours (weekdays before 9:30 AM ET or after 4:00 PM ET, weekends, FINRA holidays).
**Detection:** Frontend utility `isMarketOpen()` — hardcoded US market schedule (NYSE/NASDAQ: Mon-Fri 9:30-16:00 ET). Uses `Intl.DateTimeFormat` with `America/New_York` timezone. No API call needed. Holiday list: static array of FINRA observed holidays for current year.
**Display:** Replace green pulsing "LIVE" dot with gray static dot. Label text changes to: "Market Closed — As of Fri Mar 28, 4:00 PM ET" (uses `useMarketBriefing().briefing_date` for the timestamp). All Zone 1 data still renders (stale but useful). Movers sub-header: "Friday's Top Movers".

### Zone 2a: Opportunities — No Recommendations
**Condition:** `useRecommendations()` returns empty array (nightly task hasn't run, or no stocks meet BUY threshold).
**Display:** Glass card with same dimensions as populated state. Content: `EmptyState` with chart-bar icon, heading "No buy signals right now", subtext "Signals are recomputed each night. Check back tomorrow.", no CTA button. Card retains the green section label dot (dimmed to gray).

### Zone 2b: Action Required — No Portfolio / No Alerts
**Condition A (no portfolio):** `usePositions()` returns empty array.
**Display:** Glass card, `EmptyState` with briefcase icon, heading "Track your positions", subtext "Log transactions to get sell and watch alerts when holdings need attention.", CTA button: "Go to Portfolio →" (`router.push('/portfolio')`).

**Condition B (has portfolio, no alerts):** Positions exist but none have alerts or SELL/WATCH signals.
**Display:** Glass card, `EmptyState` with check-circle icon, heading "All clear", subtext "No alerts on your holdings. Your portfolio is on track.", no CTA. Positive tone — this is a good state.

### Zone 3: Portfolio KPIs — New User
**Condition:** `usePortfolioSummary()` returns `position_count: 0`.
**Display:**
- **KPI tiles:** All 5 tiles render with "—" as the primary value. Sub-text per tile:
  - Health: "Add positions to see grade"
  - P&L: "Log transactions to track"
  - Forecast: "Need positions for forecast"
  - Hit Rate: "Builds over time"
  - Sharpe: "Requires position history"
- **Donut:** Empty ring (single gray arc) with center text: "0 positions". No legend.
- **Sector bars:** Hidden entirely (no sectors to show). Replaced with a single-line CTA: "Start building your portfolio → [Go to Portfolio]" below the donut.

### Zone 3: Health Trend — Sparse History
**Condition:** `usePortfolioHealthHistory(7)` returns < 2 data points.
**Display:** Health KPI tile shows score + grade but no trend arrow. Sub-text: "7.8/10" (no "↑ 0.3 this week"). Trend arrow appears once 2+ snapshots exist.

### Zone 4: Alerts — No Alerts
**Condition:** `useAlerts()` returns empty array.
**Display:** Glass card (same dimensions — NOT hidden, prevents layout shift). Single centered line: "No recent alerts. Your portfolio is on track." with check-circle icon. Gray section label dot.

### Zone 5: News — No News
**Condition:** Both global briefing news and user dashboard news return empty.
**Display:** Glass card, single centered line: "No recent news for your stocks." No CTA.
**Partial condition:** Global news available but user news empty (recommendations not computed). Display global news only. No error indicator — user never knows personalized news was attempted.

### Error States (Per Zone)
When a hook fails (HTTP error, timeout), the zone shows an error variant instead of a skeleton:
- **Layout:** Same glass card dimensions as populated state. No layout shift.
- **Content:** Muted text centered in card: "[Zone name] unavailable right now" + "Retry" button (ghost style, cyan border). Retry button calls `queryClient.invalidateQueries(queryKey)`.
- **Partial failure in Zone 3:** If `usePortfolioHealth()` fails but `usePortfolioSummary()` succeeds, render the P&L and Forecast tiles normally. Show "—" for Health, Sharpe tiles with small "retry" link. Do NOT blank the entire zone.

### First-Run Experience
For a brand new user (no portfolio, no watchlist), approximately 60% of the dashboard shows empty states. This is acceptable because:
- Zone 1 (Market Pulse) renders for all users — market data is global
- Zone 5 (general market news) renders for all users
- Empty states have clear CTAs: "Go to Portfolio" (Zone 2b, Zone 3), "Go to Screener" (implicit via nav)
- The dashboard still tells a new user what the market is doing, even before they have positions

## 10b. Accessibility Specification

### Color-Only Indicators — Required Text Alternatives

| Element | Color Indicator | Required Text Alternative |
|---------|----------------|--------------------------|
| Score ring (Zone 2) | Green (≥8), orange (≥5), red (<5) | Action badge text already provides: "Strong Buy", "Buy", "Watch", "Sell". Add `aria-label="Composite score 9.2 out of 10, Strong Buy"` on the ring. |
| Metric chip values | Green/orange/red on values like "RSI 34" | Append context in parentheses: "RSI 34 (oversold)", "MACD Bullish ×over", "Piotroski 8/9 (strong)". The parenthetical IS the text alternative — no `sr-only` needed. |
| Alert severity dot (Zone 4) | Red (critical), orange (warning), cyan (info) | Add visible severity label text next to the dot: "CRITICAL", "WARNING", "INFO" in 10px uppercase, same color as the dot. Visible to all users, not just screen readers. |
| Card borders (Zone 2) | Green/orange/red glow on hover | The action badge ("Strong Buy", "Sell", "Watch") is always visible and provides the same information. No additional alternative needed. |
| Sector bar fill (Zone 3) | Green/orange/red gradient | The return% number is always visible with color. Add `aria-label="Technology sector, plus 8.4 percent return"` on each row. |
| News sentiment tags (Zone 5) | Green/red/gray background | Already have visible text: "Bullish", "Bearish", "Neutral". Sufficient. |
| Index chips (Zone 1) | Green/red left border | Change% text is already visible with color. Add `aria-label` with direction: "S&P 500, 5667, up 0.82 percent". |
| Mover MACD pill (Zone 1) | Green/red background | Already has directional text: "MACD ↑" / "MACD ↓". Sufficient. |

### Keyboard Navigation
- All clickable elements (`stock-card`, `alert-tile`, `news-card`, `sector-bar-row`, `index-chip`, `mover-row`) are rendered as `<button>` or `<a>` elements (not `<div>` with `onClick`), ensuring native keyboard focusability.
- Focus style: `outline: 2px solid var(--cyan-400); outline-offset: 2px;` via `:focus-visible`. No `:focus` ring on mouse click.
- Tab order follows visual order: Zone 1 → Zone 2a → Zone 2b → Zone 3 → Zone 4 → Zone 5.
- Within Zone 2, tab through stock cards top-to-bottom in each column, then next column.
- KPI tiles in Zone 3: only Health tile and Scorecard tile are focusable (they link to detail views). P&L, Forecast, Sharpe are display-only — no tab stop.

### Screen Reader Landmarks
- Each zone wrapped in `<section aria-labelledby="zone-X-heading">` with the section label as `<h2 id="zone-X-heading">`.
- Dashboard page has `<main role="main">`.
- Zone headings (Market Pulse, Opportunities, Action Required, Your Portfolio, Recent Alerts, Market News) are semantic headings for screen reader navigation.

## 10c. Watchlist Migration Toast

**Trigger:** First visit to `/dashboard` after the watchlist section is removed. Detected via `localStorage` key `watchlist_migration_dismissed`.
**Logic:**
```
if (!localStorage.getItem('watchlist_migration_dismissed') && previousDashboardHadWatchlist) {
  showToast()
}
```
`previousDashboardHadWatchlist` is always `true` in the migration release (hardcoded). Can be removed after one release cycle.

**Toast component:** Use existing toast/notification infrastructure (if shadcn Toast exists, use it). Content:
- Icon: arrow-right
- Text: "Your watchlist has moved to the Screener page"
- Action button: "Go to Screener" → `router.push('/screener?tab=watchlist')`
- Dismiss: click X or action button → sets `localStorage.setItem('watchlist_migration_dismissed', 'true')`
- Position: bottom-right, auto-dismiss after 10 seconds if no interaction
- Shows only once, permanently dismissed

**Screener tab badge:** The `Watchlist` tab trigger shows a count badge: "Watchlist (8)" derived from `useWatchlist().data.length`. Badge uses the existing `Badge` component with `variant="secondary"`.

## 11. Data Flow

```
Dashboard Page Load (parallel — Phase 1):
├── useMarketBriefing()            → Zone 1 (indexes, movers, sectors) + Zone 5 (general news)
├── useRecommendations()           → Zone 2a opportunity tickers
├── usePositions()                 → Zone 2b action required + Zone 3 donut
├── usePortfolioHealth()           → Zone 3 KPI (health grade, sharpe)
├── usePortfolioHealthHistory(7)   → Zone 3 KPI (health weekly trend)
├── usePortfolioSummary()          → Zone 3 KPI (P&L, total value)
├── usePortfolioForecast()         → Zone 3 KPI (90-day forecast)
├── useScorecard()                 → Zone 3 KPI (hit rate)
├── useSectors("portfolio")        → Zone 3 sector scores
└── useAlerts()                    → Zone 4

After recommendations + positions resolve (Phase 2):
├── useBulkSignals({tickers})      → Zone 2 metric strips (MACD, RSI, price)
├── useFundamentals(ticker) × 3-6  → Zone 2 metric strips (P/E, Piotroski)
└── useUserDashboardNews(tickers)  → Zone 5 (personalized ticker news)
```

Phase 1 hooks fire in parallel on page load. Phase 2 hooks fire after their dependencies resolve. Each zone renders independently: skeleton → data → error card with retry. Total HTTP requests: 10 (Phase 1) + 4-8 (Phase 2) = **14-18 requests** on cold cache. Warm cache: most return from Redis in <10ms.

## 12. Backend Gaps & Fixes

Codebase audit identified these gaps between spec and current backend/frontend state.

### B1: Top Movers — Empty Stub (Critical)
**File:** `backend/tools/market_briefing.py` line 237
**Problem:** `top_movers` is hardcoded `{"gainers": [], "losers": []}`. No implementation.
**Problem 2:** `change_pct` does NOT exist on `SignalSnapshot` model. Computing it requires joining `stock_prices` for last two closing prices per ticker — expensive window function on a TimescaleDB hypertable.
**Fix:** Two-step approach:
1. **Migration:** Add `change_pct: Float, nullable=True` column to `SignalSnapshot` model. Materialize during nightly signal computation (already reads price data).
2. **Query:** `SELECT ticker, current_price, change_pct, macd_signal_label FROM signal_snapshots WHERE computed_at = (latest) ORDER BY change_pct DESC/ASC LIMIT 4`. Fast — single table scan with index.
Return `{ticker, current_price, change_pct, macd_signal_label}` per mover. 4 gainers + 4 losers.

### B2: Recommendations Lack Signal Metrics (Critical)
**Problem:** `GET /stocks/recommendations` returns ticker + score + action but NOT MACD/RSI/P/E/Piotroski.
**Problem 2:** The bulk signals endpoint (`GET /signals/bulk`) does NOT accept a `tickers` query parameter — it's a screener endpoint with filters (index, RSI state, MACD state, sector, score range).
**Fix — Two backend changes + frontend approach:**
1. **Add `tickers` query param to `/signals/bulk`** — accept optional comma-separated ticker list. When provided, filter by those tickers instead of screener filters. This is the most impactful single change.
2. **Add `name` field to `RecommendationResponse`** — requires restructuring the recommendations query to JOIN with `stocks` table. Not a 1-line change: the query changes from `select(RecommendationSnapshot)` to `select(RecommendationSnapshot, Stock.name).join(...)`, which changes the result shape and response construction.
3. **Frontend:** After `useRecommendations()` loads, call `useBulkSignals({tickers: [top 6]})` for MACD/RSI/SMA. Call `useFundamentals(ticker)` per stock for P/E/Piotroski (cached 24h). Total: 1 bulk call + 3-6 fundamentals calls.

### B3: Positions Lack Current Signals (Critical)
**Problem:** `GET /portfolio/positions` returns alerts but no MACD/RSI for the stock.
**Fix:** Same as B2 — extract tickers with alerts from `usePositions()`, fetch via `useBulkSignals`.

### B4: News Sentiment Tags (Medium)
**Problem:** Articles from yfinance + Google News RSS have no sentiment field.
**Fix — Frontend keyword heuristic:** `classifyNewsSentiment(title: string): "bullish" | "bearish" | "neutral"` using keyword matching:
- Bullish: "beats", "surges", "upgrades", "accelerates", "record", "growth", "rises", "soars"
- Bearish: "misses", "delays", "cuts", "rejects", "falls", "downgrades", "warns", "drops", "declines"
- Neutral: everything else
No backend change. No LLM cost. Good enough for visual tagging.

### B5: Market Briefing News — Split Cache Architecture (Critical)
**File:** `backend/tools/market_briefing.py`
**Problem:** Currently fetches news for only top 3 portfolio holdings. Adding per-user recommendation tickers to the global briefing breaks the shared cache (`app:market_briefing`), causing 2300+ yfinance calls/5min at 100 users.
**Fix — Split into two endpoints:**

**1. Global Briefing (unchanged cache key `app:market_briefing`):**
Add general market news ("stock market today" Google RSS query, 3 articles). Remove per-user portfolio news from the global briefing. Also: parallelize sector ETF fetch with `asyncio.gather()` (currently sequential — 5-10s bottleneck).

**2. New endpoint: `GET /news/dashboard`** (user-scoped, cached as `user:{id}:dashboard_news`):
Accepts no params. Backend reads user's top 3 portfolio tickers + top 3 recommendation tickers. Fetches news for all 6 via yfinance + Google RSS in parallel. Max 15 articles. Cached 5 min (VOLATILE).

See §13 for full architecture details.

### B6: News Ticker + Sector Tags (Frontend only)
**Problem:** News articles don't have ticker/sector tags for the tag pills.
**Fix:** Articles from briefing already have `portfolio_ticker` field. For recommendation news, tag with source ticker. Sector derived from `stocks` table (available in bulk signals cache). Frontend assembles tag array per article: `[{type: "sentiment", value: "bullish"}, {type: "ticker", value: "MSFT"}, {type: "sector", value: "Technology"}]`.

### B7: Movers Need MACD Signal
**Problem:** Even after B1 fix, movers need MACD direction for the pill indicator.
**Fix:** When computing movers from `signal_snapshots`, include `macd_signal` field (already stored per snapshot). No extra computation needed.

### No Backend Changes Needed
- `/portfolio/health` — all fields present (health_score, grade, weighted_sharpe, weighted_beta)
- `/forecasts/portfolio` — 90-day horizon with expected_return_pct, lower_pct, upper_pct
- `/recommendations/scorecard` — overall_hit_rate + total_outcomes
- `GET /alerts` — full endpoint with severity, title, ticker, unread_count

## 13. News Architecture — Split Cache Strategy

### The Cache Problem
The current market briefing is cached globally (`app:market_briefing`), shared across all users. If we add per-user recommendation tickers to the briefing, it becomes per-user, breaking the global cache. At 100 users with 5-min TTL, that means 2300+ external API calls per 5 minutes — yfinance rate limits at ~2000 req/hour. **This will fail at scale.**

### Solution: Two-Tier Cache Split

**Tier 1: Global Briefing (shared, cached globally)**
Cache key: `app:market_briefing` (existing)
Contents: indexes + sector performance + top movers + general market news ("stock market today" RSS query)
TTL: 5 min (VOLATILE)
External calls: ~17 yfinance + 1 Google RSS (once per 5 min, total, regardless of user count)

**Tier 2: User News (per-user, lazy-loaded)**
Cache key: `user:{id}:dashboard_news`
Contents: news for portfolio holdings (top 3) + recommendation tickers (top 3)
TTL: 5 min (VOLATILE)
External calls: 6 tickers × 2 sources = 12 calls per unique user per 5 min
Triggered by: `useUserDashboardNews()` — fires AFTER `useRecommendations()` resolves (needs the tickers)

This preserves the expensive global briefing cache while allowing per-user news. At 100 concurrent users, worst case: 17 global calls + (100 × 12) = 1217 calls/5min. With deduplication of popular tickers across users, likely much lower.

**Alternative optimization (future):** Pre-compute news for top 20 most-recommended tickers globally via Celery beat task. Cache as `app:recommended_news`. Covers most users with zero per-user cost.

### Frontend Loading Strategy

```
Page Load (parallel):
├── useMarketBriefing()                    → Zone 1 + Zone 5 (general market news)
├── useRecommendations()                   → Zone 2a tickers
├── usePositions()                         → Zone 2b tickers
└── ... other hooks ...

After recommendations + positions resolve:
└── useUserDashboardNews(tickers[])        → Zone 5 (personalized news, appended)
```

Zone 5 renders in two phases:
1. **Immediate:** General market news from global briefing (available on first render)
2. **Progressive:** Per-user ticker news fills in as it loads (1-3 second delay)

### News Card Assembly (Frontend)
```
article from backend → {title, link, publisher, published, source, portfolio_ticker?}
                ↓
Frontend enriches → {
  ...article,
  sentiment: classifyNewsSentiment(title),       // keyword heuristic
  ticker_tag: article.portfolio_ticker || null,   // from response
  sector_tag: lookupSector(article.portfolio_ticker), // from bulk signals cache
}
                ↓
Render as NewsCard with tag pills
```

### Sentiment Heuristic (Frontend)
`classifyNewsSentiment(title: string): "bullish" | "bearish" | "neutral"`
- Bullish: "beats", "surges", "upgrades", "accelerates", "record", "growth", "rises", "soars"
- Bearish: "misses", "delays", "cuts", "rejects", "falls", "downgrades", "warns", "drops", "declines"
- Neutral: everything else
No backend change. No LLM cost.

### News Data Sources (no changes)
- **yfinance** (`Ticker.news`): Free, 500-1500ms, 10 articles/ticker
- **Google News RSS** (`news.google.com/rss`): Free, 800-3000ms, 10 articles/ticker
- **SerpAPI**: NOT used for dashboard news (reserved for agent web search tool, $0.025/query)
- **Cache:** Redis `VOLATILE` tier (5 min TTL with jitter)
- **Persistence:** None — news is ephemeral (fetched on-demand, cached briefly)

### Recommendation News Fallback
Recommendations are generated by a nightly Celery task. If the user loads the dashboard before the task runs (e.g., first thing Monday), the recommendations table may be empty. In this case, `useUserDashboardNews()` falls back to portfolio-only news. This is best-effort — no error state.

## 14. Signal Data Strategy for Stock Cards

To avoid N+1 API calls, stock cards in Zones 2a/2b use a layered data approach:

```
Layer 1: useRecommendations() / usePositions()
  → ticker, composite_score, action/alerts
  → Renders: score ring, ticker, action badge

Layer 2: useBulkSignals({tickers: [top 6 tickers]})
  → rsi_value, rsi_signal, macd_signal, sma_signals, sharpe_ratio, price
  → Renders: MACD pill, RSI chip, SMA chip, Price chip, Change% chip

Layer 3: useFundamentals(ticker) × 3-6 calls (cached 24h)
  → pe_ratio, piotroski_score, fcf_yield
  → Renders: P/E chip, Piotroski chip (optional — renders when available)
```

Zone 2 renders Layers 1-2 immediately (fast). Layer 3 fills in progressively. If fundamentals are slow or unavailable, the card still looks complete with Layer 1-2 metrics.

## 15. Out of Scope

- Portfolio health history chart (belongs on portfolio detail page)
- Sector forecasts on dashboard (belongs on sectors page)
- Observability data anywhere on dashboard or chat
- WelcomeBanner redesign (deferred)
- Real-time WebSocket updates (future phase)
- LLM-based news sentiment analysis (keyword heuristic is sufficient for v1)
- News persistence to database (ephemeral + Redis cache is fine for now)
- SerpAPI for news (reserved for agent tools, too expensive for dashboard)
- Navigation restructuring (current 4-item nav is correct — no `/market` or `/watchlist` pages needed)
- Celery news pre-warming tasks (on-demand with caching is sufficient given 5-min TTL)

## 16. Field-Level Data Mapping — Critical Audit

Every display field on every component mapped to a confirmed API field. Gaps flagged with fixes.

### Component 1: IndexChip
| Display Field | API Field | Source | Status |
|---|---|---|---|
| name | `name` | `useIndexes()` → `IndexResponse` | ✅ |
| value (price) | `price` | `useMarketBriefing()` → `IndexPerformance` | ⚠️ Exists in briefing but NOT in `IndexResponse`. Use briefing data, not indexes endpoint. |
| change% | `change_pct` | `useMarketBriefing()` → `IndexPerformance` | ⚠️ Same — briefing has it, indexes endpoint does not. |

**Fix:** IndexChip must consume data from `useMarketBriefing().indexes` (which has `price` + `change_pct`), NOT from `useIndexes()` (which only has name/slug/stockCount).

### Component 2: MoverRow
| Display Field | API Field | Source | Status |
|---|---|---|---|
| ticker | `ticker` | `useMarketBriefing().top_movers` | ❌ Empty stub — B1 fix |
| price | `current_price` | signal_snapshots table | ❌ B1 fix |
| MACD direction | `macd_signal_label` | signal_snapshots table | ❌ B1 fix |
| change% | computed | `(current - prev_close) / prev_close` | ❌ B1 fix — need `previous_close` or compute from price history |

**Fix (B1):** Query `signal_snapshots` for top gainers/losers by daily change. Return `{ticker, current_price, change_pct, macd_signal_label}`. Change% must be computed — `signal_snapshots` has `current_price` but NOT `previous_close`. **Option:** Join with most recent `price_history` entry for prev close, OR add a `change_pct` column to snapshots during signal computation. Simplest: compute from the stock's latest two prices in `price_history`.

### Component 3: SignalStockCard (Opportunities — Buy)
| Display Field | API Field | Source | Status |
|---|---|---|---|
| composite_score | `composite_score` | `useRecommendations()` | ✅ |
| ticker | `ticker` | `useRecommendations()` | ✅ |
| company_name | `name` | ❌ NOT in `RecommendationResponse` | ❌ Missing |
| action_badge | derived from `action` field | `useRecommendations()` | ✅ |
| price | `current_price` | `useBulkSignals()` → `BulkSignalItem` | ✅ (Layer 2) |
| change% | ❌ NOT in `BulkSignalItem` | — | ❌ Missing |
| MACD signal | `macd_signal` | `useBulkSignals()` → `BulkSignalItem` | ✅ (Layer 2) |
| RSI value | `rsi_value` | `useBulkSignals()` → `BulkSignalItem` | ✅ (Layer 2) |
| P/E | `pe_ratio` | `useFundamentals()` | ✅ (Layer 3, nullable) |
| Piotroski | `piotroski_score` | `useFundamentals()` | ✅ (Layer 3, nullable) |
| reason_text | `reasoning` | `useRecommendations()` | ⚠️ JSONB, may be null — fallback to `buildSignalReason()` |

**Gaps to fix:**
1. **company_name:** `RecommendationResponse` lacks it. **Fix:** Look up from `useBulkSignals()` response which includes stock name, OR add `name` to `RecommendationResponse` schema (1-line backend change — join with stocks table).
2. **change%:** Not in `BulkSignalItem`. **Fix:** Compute on frontend from `current_price` vs `price_history[-2]` (bulk signals includes `price_history` array). OR add `change_pct` to `BulkSignalItem` during signal computation.

### Component 4: SignalStockCard (Action Required — Sell/Watch)
| Display Field | API Field | Source | Status |
|---|---|---|---|
| composite_score | ❌ NOT in `PositionWithAlerts` | — | ❌ Missing — use `useBulkSignals()` |
| ticker | `ticker` | `usePositions()` | ✅ |
| company_name | ❌ NOT in `Position` | — | ❌ Missing — look up from bulk signals or stocks cache |
| action_badge | derived from alert severity | `usePositions()` alerts | ✅ |
| current_price | `current_price` | `usePositions()` | ✅ (nullable) |
| change% | ❌ NOT in `Position` | — | ❌ Missing — compute from bulk signals |
| MACD/RSI | ❌ NOT in `Position` | — | ❌ Missing — use `useBulkSignals()` |
| sector | `sector` | `usePositions()` | ✅ (nullable) |
| alert details | `alerts[].message` | `usePositions()` | ✅ |

**Fix:** Same layered approach as Component 3. Extract tickers from positions with alerts → `useBulkSignals({tickers})` → merge data.

### Component 5: PortfolioKPITile — Health
| Display Field | API Field | Source | Status |
|---|---|---|---|
| grade | `grade` | `usePortfolioHealth()` | ✅ |
| score (0-10) | `health_score` | `usePortfolioHealth()` | ✅ |
| weekly_trend | ❌ NOT in `PortfolioHealthResult` | — | ❌ Missing |

**Fix:** Call `usePortfolioHealthHistory(days=7)` → `GET /portfolio/health/history?days=7`. Compare latest `health_score` with 7-day-ago score. Compute delta on frontend. This is a lightweight call (returns ~7 rows). Add `usePortfolioHealthHistory` to hooks.

### Component 6: PortfolioKPITile — P&L ✅ Complete
| Display Field | API Field | Source | Status |
|---|---|---|---|
| unrealized_pnl ($) | `unrealized_pnl` | `usePortfolioSummary()` | ✅ |
| unrealized_pnl_pct (%) | `unrealized_pnl_pct` | `usePortfolioSummary()` | ✅ |

### Component 7: PortfolioKPITile — Forecast ✅ Complete
| Display Field | API Field | Source | Status |
|---|---|---|---|
| expected_return_pct | `horizons[].expected_return_pct` | `usePortfolioForecast()` | ✅ (filter for 90-day) |
| lower_pct | `horizons[].lower_pct` | `usePortfolioForecast()` | ✅ |
| upper_pct | `horizons[].upper_pct` | `usePortfolioForecast()` | ✅ |

**Note:** Must filter `horizons` array for `horizon_days === 90`. Array could be empty if no forecasts exist — show "—" fallback.

### Component 8: PortfolioKPITile — Hit Rate ✅ Complete
| Display Field | API Field | Source | Status |
|---|---|---|---|
| overall_hit_rate | `overall_hit_rate` | `useScorecard()` | ✅ (0-1 float, display as %) |
| total_outcomes | `total_outcomes` | `useScorecard()` | ✅ |

### Component 9: PortfolioKPITile — Sharpe ✅ Complete
| Display Field | API Field | Source | Status |
|---|---|---|---|
| weighted_sharpe | `metrics.weighted_sharpe` | `usePortfolioHealth()` | ✅ (nullable — show "—" if null) |

### Component 10: AllocationDonut ✅ Complete
| Display Field | API Field | Source | Status |
|---|---|---|---|
| sectors[].sector | `sectors[].sector` | `usePortfolioSummary()` | ✅ |
| sectors[].pct | `sectors[].pct` | `usePortfolioSummary()` | ✅ |
| total_value | `total_value` | `usePortfolioSummary()` | ✅ |
| position_count | `position_count` | `usePortfolioSummary()` | ✅ |

### Component 11: SectorPerformanceBars
| Display Field | API Field | Source | Status |
|---|---|---|---|
| sector_name | `sector` | `useMarketBriefing().sector_performance` | ✅ |
| return% | `change_pct` | `useMarketBriefing().sector_performance` | ✅ (1-day ETF change) |
| score | ❌ NOT in `SectorPerformance` | — | ❌ Missing |
| bar_fill_width | derived from `change_pct` | frontend | ✅ |

**Fix for sector score:** Two options:
- **(a) Frontend aggregation:** From `usePositions()` + `useBulkSignals()`, compute average composite_score per sector for held stocks. This gives a "your portfolio's sector score" which is more relevant than market-wide.
- **(b) Backend endpoint:** Use `GET /sectors?scope=portfolio` which already returns `avg_score` per sector in `SectorSummaryResponse`.

**Recommendation:** Option (b) — `useSectors("portfolio")` already exists and returns `avg_score` per sector. Map `sector_performance` (for return%) with `sectors` (for avg_score) by sector name.

**CRITICAL: Sector name mismatch.** Market briefing uses ETF sector names while yfinance uses GICS names. At least 4 don't match.

**Fix:** Create `backend/utils/sectors.py` with `SECTOR_NAME_MAP` dict AND a `normalize_sector(name: str) -> str` function. Also export as a frontend constant in `frontend/src/lib/sectors.ts`.

```python
# Canonical name → [aliases from different sources]
SECTOR_ALIASES: dict[str, list[str]] = {
    "Technology":           ["Technology", "Information Technology"],
    "Healthcare":           ["Healthcare", "Health Care"],
    "Financial Services":   ["Financial Services", "Financials"],
    "Consumer Cyclical":    ["Consumer Cyclical", "Consumer Discretionary"],
    "Consumer Defensive":   ["Consumer Defensive", "Consumer Staples"],
    "Energy":               ["Energy"],
    "Industrials":          ["Industrials"],
    "Basic Materials":      ["Basic Materials", "Materials"],
    "Utilities":            ["Utilities"],
    "Real Estate":          ["Real Estate"],
    "Communication Services": ["Communication Services", "Communications", "Telecom"],
}

# Reverse lookup: any alias → canonical name
SECTOR_NORMALIZE: dict[str, str] = {
    alias: canonical
    for canonical, aliases in SECTOR_ALIASES.items()
    for alias in aliases
}

def normalize_sector(name: str) -> str:
    return SECTOR_NORMALIZE.get(name, name)
```

**Where applied:**
1. **Backend:** `market_briefing.py` uses `normalize_sector()` when returning `sector_performance` so all sector names match the yfinance canonical form.
2. **Frontend:** `SectorPerformanceBars` component normalizes both data sources before merge.
3. **ETF gap:** `Communication Services` has ETF `XLC` — add to `SECTOR_ETFS` dict in `market_briefing.py`.

### Component 12: AlertTile ✅ Complete
| Display Field | API Field | Source | Status |
|---|---|---|---|
| severity | `severity` | `useAlerts()` | ✅ |
| ticker | `ticker` | `useAlerts()` | ✅ (nullable for portfolio-wide) |
| title | `title` | `useAlerts()` | ✅ |
| created_at | `created_at` | `useAlerts()` | ✅ |

### Component 13: NewsCard
| Display Field | API Field | Source | Status |
|---|---|---|---|
| headline | `title` | `useMarketBriefing().portfolio_news` | ✅ |
| publisher | `publisher` | `useMarketBriefing().portfolio_news` | ✅ (nullable) |
| published | `published` | `useMarketBriefing().portfolio_news` | ✅ (nullable) |
| link | `link` | `useMarketBriefing().portfolio_news` | ✅ |
| sentiment_tag | ❌ NOT in API | frontend heuristic | ✅ via B4 fix |
| ticker_tag | `portfolio_ticker` | briefing enrichment | ⚠️ Added at runtime, not in schema |
| sector_tag | ❌ NOT in API | frontend lookup | ✅ via B6 fix |

### Summary: Completeness Score

| Component | Complete | Gaps | Fix Complexity |
|---|---|---|---|
| IndexChip | ⚠️ | Use briefing data, not indexes | Low — change data source |
| MoverRow | ❌ | B1: implement top_movers | Medium — new backend query |
| SignalStockCard (Buy) | ⚠️ | company_name, change% | Low — bulk signals + 1 schema field |
| SignalStockCard (Sell) | ⚠️ | score, name, change%, signals | Low — bulk signals merge |
| KPI: Health | ⚠️ | weekly trend needs history call | Low — new hook |
| KPI: P&L | ✅ | — | — |
| KPI: Forecast | ✅ | — | — |
| KPI: Hit Rate | ✅ | — | — |
| KPI: Sharpe | ✅ | — | — |
| AllocationDonut | ✅ | — | — |
| SectorPerfBars | ⚠️ | Score from useSectors() | Low — merge two data sources |
| AlertTile | ✅ | — | — |
| NewsCard | ⚠️ | Sentiment + sector (frontend) | Low — heuristic |

### Additional Hooks Needed (revised)

| Hook | Endpoint | Purpose |
|---|---|---|
| `useMarketBriefing()` | `GET /market/briefing` | Zone 1 indexes + movers + Zone 5 news |
| `usePortfolioHealth()` | `GET /portfolio/health` | Zone 3 health grade + Sharpe |
| `usePortfolioHealthHistory(days)` | `GET /portfolio/health/history?days=N` | Zone 3 health weekly trend |
| `useSectors("portfolio")` | `GET /sectors?scope=portfolio` | Zone 3 sector scores (existing endpoint, new hook usage) |

### Backend Changes Needed (Summary)

| Change | Files | Complexity | Notes |
|--------|-------|-----------|-------|
| **Migration: add `change_pct` to `SignalSnapshot`** | `models/signal.py`, new Alembic migration | Medium | Materialized during nightly signal computation |
| **`/signals/bulk`: add `tickers` query param** | `routers/stocks/signals.py`, `schemas/stock.py` | Low | Optional param, filter by ticker list |
| **`RecommendationResponse`: add `name` field** | `routers/stocks/recommendations.py`, `schemas/stock.py` | Medium | Requires JOIN restructure + response construction change (not 1-line) |
| **`market_briefing.py`: implement `top_movers`** | `tools/market_briefing.py` | Medium | Query signal_snapshots for top gainers/losers by `change_pct` |
| **`market_briefing.py`: add general market news** | `tools/market_briefing.py` | Low | Add Google RSS query for "stock market today" |
| **`market_briefing.py`: parallelize sector ETF fetch** | `tools/market_briefing.py` | Low | Wrap sequential ETF fetches in `asyncio.gather()` |
| **New endpoint: `GET /news/dashboard`** | new `routers/news.py` or extend `routers/market.py` | Medium | Per-user news aggregation (portfolio + recommendation tickers) |
| **Sector name normalization map** | shared utility (`backend/utils/sectors.py` or similar) | Low | Map yfinance GICS names ↔ ETF sector names |

## 17. Testing Strategy

- **Component tests:** Each new component (SignalStockCard, MetricsStrip, ScoreRing, PortfolioKPITile, HealthGradeBadge, SectorPerformanceBars, AlertTile, MoverRow) gets 3-5 tests: renders with data, loading skeleton, **empty state**, error state with retry, color-coding logic.
- **Hook tests:** New hooks (useMarketBriefing, usePortfolioHealth, usePortfolioHealthHistory, useUserDashboardNews) tested for query key, staleTime, error handling, empty response handling.
- **Backend tests:** Top movers query, recommendation name join, bulk signals tickers filter, news dashboard endpoint, sector name normalization.
- **Integration:** Dashboard page renders all 5 zones with mocked data. Chat panel toggle adapts layout. Empty state variant with no portfolio data.
- **Accessibility:** Color-only indicators have text alternatives. Keyboard tab order through all clickable elements. Focus-visible rings on interactive elements.
- **Visual regression:** Compare against `docs/mockups/dashboard-bulletin-v3.html` for layout fidelity.

## Appendix A: Expert Review Findings (Addressed)

Review conducted by UX Architect and Backend Architect perspectives. All Critical and Important findings have been incorporated into the spec above.

### UX Review — Key Decisions Made
| Finding | Resolution | Spec Section |
|---------|-----------|-------------|
| Empty states undefined | Added §10a with per-zone empty states and first-run CTAs | §10a |
| Color-only indicators | Added text alternatives requirement + metric chip context labels | §2, §3 Zone 2 |
| Alerts below fold | Zone 2b explicitly designated as primary alert surface | §3 Zone 2 |
| Metric chip overload | Visual hierarchy (primary/secondary clusters) + mobile 4-chip cap | §3 Zone 2 |
| Font sizes too small | Minimum 11px labels, 12px values | §2 |
| No market hours indicator | Session status on Market Pulse label | §2 |
| Keyboard focus states | `:focus-visible` requirement added | §2 |
| Mobile scroll depth | Cap visible cards per zone + "See all" links | §10 |
| Watchlist discoverability | One-time migration toast + badge count on screener tab | §5 |

### Backend Review — Key Decisions Made
| Finding | Resolution | Spec Section |
|---------|-----------|-------------|
| Per-user cache breaks at scale | Split: global briefing + per-user news endpoint | §13 |
| Sector name mismatch | SECTOR_NAME_MAP normalization utility | §16 Component 11 |
| `change_pct` not on SignalSnapshot | New migration to materialize during signal computation | §12 B1 |
| Bulk signals lacks tickers param | Add `tickers` query param to endpoint | §12 B2 |
| Recommendation name is a query restructure | Documented as Medium complexity, not 1-line | §12 B2 |
| Briefing ETF fetch is sequential bottleneck | Parallelize with `asyncio.gather()` | §12 B5 |
| Recommendations may be empty on first load | Best-effort fallback documented | §13 |
| Health history may be sparse | Frontend handles < 2 data points (no trend arrow) | §16 Component 5 |

### Nice-to-Have (Deferred to Future Iteration)
- Mini sparkline on P&L KPI tile
- "Ask about this" chat trigger on stock cards
- Earnings calendar as distinct mini-zone
- Zone 5 (News) collapsible on mobile
- Sector bar score tooltip with component breakdown
- Featured first Opportunity card (larger size)
