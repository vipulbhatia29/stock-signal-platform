# Lovable → Production Migration — Gap Analysis

> **Session 37 Brainstorm Output**
> **Date:** 2026-03-19
> **Status:** Requirements discovery complete. Next: `/sc:workflow` for migration plan.

---

## 1. Entirely NEW Features (not in our app)

### 1.1 New Page: Sectors (`/sectors`) — HIGH PRIORITY
- Sector allocation overview (AllocationDonut)
- Collapsible sector accordions (sector name, stock count, avg score, avg return)
- Expanded view: full comparison table per sector (all signals + performance)
- **Correlation matrix** with heatmap + table views
  - Heatmap: color-coded grid (green=low correlation → red=high)
  - Table: ranked correlation list with interpretation text
- Portfolio-only toggle (filter to held stocks)
- **Backend needed:** `GET /api/v1/sectors` (aggregate by sector), `GET /api/v1/sectors/{sector}/correlation` (price correlation computation)

### 1.2 Benchmark Comparison Chart — MEDIUM PRIORITY
- Stock detail page: normalized % change comparison
- 3 lines: Stock (cyan), S&P 500 (green dashed), NASDAQ (amber dashed)
- Zero reference line
- **Backend needed:** Index price history (^GSPC, ^IXIC via yfinance)

### 1.3 Candlestick Chart Toggle — MEDIUM PRIORITY
- Stock detail: Line/Candle toggle button group
- Candle chart: green bars for bullish (close≥open), red for bearish
- **Backend needed:** None — OHLC data already in `stock_prices` table

### 1.4 Action Required Section — MEDIUM PRIORITY
- Dashboard: recommendation rows with action icon, confidence level, reasoning text
- Links to stock detail
- Shows "Held" badge for portfolio stocks
- **Backend needed:** Partially — `recommendation_snapshots` exist but no `reasoning` text field. Need to add reasoning to recommendation generation.

### 1.5 Per-Stock Refresh Indicator — MEDIUM PRIORITY
- `RefreshIndicator` component on every stock card/row
- Relative time display ("just now", "5m ago", "6h ago")
- Stale detection (>12 hours = amber warning)
- Click to refresh individual stock
- Spinning animation during refresh
- **Backend needed:** `last_fetched_at` already on Stock model — need to expose via watchlist/screener API responses

### 1.6 Framer Motion Animations — LOW PRIORITY
- Staggered fade-up on all card grids (`initial={{ opacity: 0, y: 12 }}`)
- Slide-in for settings sheet, modal scale-in
- Pulsing dots for thinking indicator
- **Backend needed:** None — `npm install framer-motion`

### 1.7 Auth Redesign — LOW PRIORITY
- Split-panel: brand showcase (left) + form (right)
- Google OAuth button (UI stub — backend OAuth is Phase 5+)
- Animated grid background, glowing orbs, sparkline decoration
- Input focus glow effects, submit button glow
- "Remember me" checkbox, "Forgot password?" link
- **Backend needed:** None for UI. Google OAuth requires OAuth2 provider setup (future).

### 1.8 Notification Bell — DEFERRED (Phase 5)
- Bell icon in topbar
- **Backend needed:** Full notification system (Phase 5)

### 1.9 ScoreBar Component — LOW PRIORITY
- 10-segment horizontal bar showing score visually
- Color-coded: ≥8 green, ≥5 amber, <5 red
- Used in watchlist cards and screener rows
- **Backend needed:** None

### 1.10 Chat-Open Grid Adaptation — LOW PRIORITY
- Every page reads `chatOpen` state and adjusts grid columns
- Dashboard: 5→3 columns, Screener: adjusts card widths
- **Backend needed:** None — React context pattern

---

## 2. REDESIGNED Features (exists but different visual/UX)

### 2.1 Sidebar
| Current | Lovable |
|---------|---------|
| No logo glow | Logo with `drop-shadow` cyan glow |
| No active left bar | Active cyan `w-0.5` left indicator |
| No Sectors item | Sectors (PieChart icon) added |
| Avatar-based logout | Dedicated logout button with destructive hover |
| CSS tooltips | shadcn Tooltip component |

### 2.2 Topbar
| Current | Lovable |
|---------|---------|
| Search with placeholder | Centered search with `/` keyboard hint + Refresh All inside |
| No bell | Notification bell icon |
| Market status chip | Market status with pulsing green dot |
| Signal count shows number | Signal count with Activity icon + styled badge |
| AI Analyst toggle | AI Analyst toggle with active cyan bg + glow border |

### 2.3 Dashboard Layout
| Current | Lovable |
|---------|---------|
| KPI tiles → Watchlist | KPI tiles → Market Indexes → Action Required + Sector Allocation → Watchlist |
| No market indexes | 3 index cards (S&P, NASDAQ, Dow) with sparkline |
| No recommendations | Action Required section with 5 recommendation rows |
| Simple watchlist cards | Cards with Held badge, ScoreBar, RefreshIndicator, SignalBadge |
| Allocation tile shows "No positions" | Allocation tile links to `/sectors` |

### 2.4 Screener
| Current | Lovable |
|---------|---------|
| Score range slider | ScoreBar + ScoreBadge inline |
| No "Fresh" column | RefreshIndicator per row |
| No "Held" indicator | Briefcase icon for portfolio stocks |
| Index filter dropdown | Removed (uses sector filter only) |
| DensityProvider toggle | Simple Compact/Comfortable text button |

### 2.5 Stock Detail
| Current | Lovable |
|---------|---------|
| No close button | Close button (X) at top |
| Score badge small | Large score badge next to ticker |
| No dollar change | Price + change% + ($dollar change) |
| No refresh indicator | RefreshIndicator next to price |
| Line chart only | Line/Candle toggle |
| No benchmark chart | vs. Benchmarks (% Change) section |
| Signal cards: value + badge | Signal cards: value + badge + **description text** + meter bar (RSI) |
| No watchlist toggle on detail | Bookmark/BookmarkCheck toggle button |

### 2.6 Portfolio
| Current | Lovable |
|---------|---------|
| No value chart overlay | Portfolio value chart + cost basis dashed overlay |
| Alert badges as text | Alert icons (AlertOctagon critical, AlertTriangle warning) |
| Settings as Sheet | Settings as framer-motion slide-in with blur backdrop |
| Transaction dialog | Transaction modal with BUY/SELL toggle + scale animation |

### 2.7 Chat Panel
| Current | Lovable |
|---------|---------|
| Two flat buttons for agent | Styled cards with icons (BarChart3/Globe) + "Choose an Agent" heading |
| Suggestion chips clickable (auto-send) | Suggestion chips fill input (don't auto-send) |
| Tool card shows raw JSON params | Tool card truncated with Copy/CSV buttons |
| No markdown table rendering | Custom markdown table renderer |
| Thinking: "Analyzing your question..." text | 3 pulsing cyan dots + text |

---

## 3. Backend Requirements Summary

| Feature | Endpoint | Effort |
|---------|----------|--------|
| Sectors page | `GET /api/v1/sectors` — stocks grouped by sector with avg score/return | Medium |
| Correlation matrix | `GET /api/v1/sectors/{sector}/correlation` — price correlation computation | High |
| Benchmark data | Index price history for ^GSPC, ^IXIC (yfinance or cache) | Medium |
| Recommendation reasoning | Add `reasoning: str` field to recommendation generation | Low |
| Per-stock refresh timestamp | Expose `last_fetched_at` in watchlist + screener API responses | Low |
| Google OAuth | OAuth2 provider (Google Cloud Console + callback endpoint) | Medium (deferred) |
| Notification system | Full notification backend | High (Phase 5) |

---

## 4. Migration Strategy

### Phase UI-1: Shell + Shared Components (~1 day)
- Sidebar redesign (logo glow, Sectors nav, active indicator, logout)
- Topbar redesign (centered search, `/` hint, Refresh All, bell stub, pulsing market dot)
- Install framer-motion, add `card2`/`hov`/`pulse-subtle` tokens
- New shared components: ScoreBar, RefreshIndicator
- Updated: ScoreBadge, SignalBadge, ChangeIndicator styling
- Chat-open grid adaptation (ChatContext)

### Phase UI-2: Dashboard + Auth (~1 day)
- Dashboard layout: Market Indexes + Action Required + Sector Allocation
- Watchlist cards: Held badge, ScoreBar, RefreshIndicator
- Stat tiles: accent gradient bar, donut variant
- Auth pages: split panel, brand showcase, form styling (Google OAuth as stub)

### Phase UI-3: Screener + Stock Detail (~1 day)
- Screener: ScoreBar inline, Fresh column, Held badge, Performance tab
- Stock Detail: header redesign, candlestick toggle, signal descriptions, benchmark chart
- Backend: expose `last_fetched_at`, add benchmark price data

### Phase UI-4: Portfolio + Sectors (~1-2 days)
- Portfolio: value chart with cost basis overlay, alert icons, settings sheet, transaction modal
- Sectors page: new page, sector endpoint, allocation donut, accordion, comparison table
- Backend: sectors endpoint, correlation computation

### Phase UI-5: Polish + Animations (~0.5 day)
- Framer-motion staggered animations on all grids
- Focus glow effects on inputs
- Button glow on CTAs
- Scrollbar styling
- Chat-open responsive grid on all pages

---

## 5. Open Questions for User

1. **Google OAuth** — Do you want the UI stub now, or wait until we have the backend OAuth flow?
2. **Sectors correlation** — The heatmap requires significant computation. Do you want this in the initial migration or deferred?
3. **Notification bell** — Stub icon now (no backend), or wait until Phase 5 notification system?
4. **Framer Motion** — Should we add this now (bundle size impact ~30KB gzipped) or defer?
5. **Candlestick data** — OHLC exists in DB but may need a new API response format for the candle chart. Acceptable?
6. **Recommendation reasoning** — The `reasoning` text field doesn't exist in our recommendation engine. Should we generate it from the signal data, or is it an LLM-generated explanation?

---

## 6. What Stays the Same

These features are equivalent in both implementations and need no migration:
- JWT cookie auth flow (backend)
- Portfolio FIFO engine
- Signal computation (RSI, MACD, SMA, Bollinger, composite score)
- Fundamentals + Piotroski F-Score
- Dividend tracking
- Divestment rules engine
- Rebalancing suggestions
- TanStack Query data fetching pattern
- Chat streaming (NDJSON)
- Tool orchestration (LangGraph)
