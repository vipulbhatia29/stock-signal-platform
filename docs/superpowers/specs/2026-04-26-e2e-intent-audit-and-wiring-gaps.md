# E2E Intent Audit & Wiring Gap Resolution

**Epic:** KAN-400 (UI Overhaul — true completion)
**Story:** KAN-504 (redefined)
**Date:** 2026-04-26
**Author:** Session 138 — identified during visual verification

---

## 1. Problem Statement

The backend is essentially complete. ~60 API endpoints exist, ~33 frontend hooks exist, 11 pages exist. But **having code is not the same as having working flows.** Session 138 visual verification found the first gap within 2 minutes: searching for "apple" and clicking "Add" returns a 404 because the frontend calls `addToWatchlist` without first calling `ingest`.

A code-level audit (grep for hooks, check imports) said the stock add flow was "✅ Complete." It was wrong. The only way to find wiring gaps is to **click through every flow end-to-end** and compare actual behavior against PRD/FSD intent.

This is not a testing task. This is a **product completeness audit** — the true scope of KAN-400 (UI Overhaul).

---

## 2. Approach

For each user journey defined in the PRD/FSD:

1. **Define the intent** — what should happen per spec (PRD section, FSD FR#)
2. **Click through it with Playwright** — screenshot every step
3. **Compare actual vs expected** — document the delta
4. **Classify the gap** — wiring bug (frontend doesn't call API), missing page, missing nav, missing UX feedback
5. **Fix the wiring** — backend exists, wire the frontend
6. **Leave Playwright test as regression guard** — so it never breaks again

---

## 3. User Journeys to Audit

### Journey 1: Stock Discovery → Add → View (PRD 5.1, 5.19 | FSD FR-2, FR-3)

**Intent:** User searches for a stock (e.g., "apple"). If not in universe, system ingests 10Y of data (prices, signals, fundamentals, news, convergence, forecast). User lands on stock detail page with full analysis.

**Steps to validate:**
- [ ] Search bar opens, typing filters results
- [ ] External stocks show "Add from market" with + icon
- [ ] Clicking external stock triggers ingest (not just watchlist add)
- [ ] Progress indicator shows during ingest (10Y fetch takes seconds)
- [ ] On success → navigate to `/stocks/AAPL`
- [ ] Stock detail page shows: price chart, signals, fundamentals, convergence, forecast, sentiment, news, intelligence
- [ ] If stock IS in universe but stale → delta refresh triggered
- [ ] If stock IS in universe and fresh → navigates directly

**Known gap:** Frontend calls `addToWatchlist` (404) instead of `ingest` → `addToWatchlist` → navigate. `handleAddTicker` in `layout.tsx` needs rewrite.

---

### Journey 2: Stock Detail Page — Full Section Audit (PRD 5.1-5.14 | FSD FR-3, FR-5, FR-11, FR-26)

**Intent:** Stock detail page is the product's core value — everything about a stock in one scrollable page with section navigation.

**Steps to validate:**
- [ ] Navigate to `/stocks/AAPL` (after adding)
- [ ] SectionNav renders all sections and jump-links work
- [ ] **Price Chart** — line chart renders, candlestick toggle works, OHLC data loads
- [ ] **Signals** — RSI, MACD, SMA, Bollinger cards render with values, composite score ring
- [ ] **Signal History** — chart shows signal trend over time
- [ ] **Convergence** — ConvergenceCard shows signal alignment, divergence alert if applicable
- [ ] **Benchmark** — comparison chart vs SPY renders
- [ ] **Risk Analytics** — Sortino, max drawdown, alpha, beta from QuantStats
- [ ] **Fundamentals** — P/E, PEG, margins, ROE, analyst targets, Piotroski score
- [ ] **Forecast** — Prophet chart with 90/180/270d horizons, confidence intervals
- [ ] **Track Record** — ForecastTrackRecord chart with direction accuracy KPIs
- [ ] **Intelligence** — insider trades, upgrades/downgrades, EPS revisions
- [ ] **Sentiment** — SentimentCard with trend chart, article list
- [ ] **News** — news feed with sentiment color coding
- [ ] **Dividends** — dividend history if applicable
- [ ] **Manual refresh button** — user can trigger signal/data refresh (FSD FR-3.3 says stale signals flagged but no refresh UX exists)

---

### Journey 3: Screener → Filter → Select (PRD 5.6 | FSD FR-7)

**Intent:** Browse, filter, and sort the stock universe. Click a stock to view its detail.

**Steps to validate:**
- [ ] Screener page loads with stock table
- [ ] Column tabs work (Overview / Signals / Performance)
- [ ] Filters: index dropdown, sector, RSI range, MACD, score slider
- [ ] Grid view toggle shows sparkline cards
- [ ] Pagination works (next/prev, page count)
- [ ] Watchlist tab filters to watchlisted stocks only
- [ ] Clicking a row navigates to `/stocks/{ticker}`
- [ ] Sentiment column shows values (Spec B wiring)
- [ ] Back navigation from stock detail returns to screener (with filters preserved?)

---

### Journey 4: Portfolio Management (PRD 5.7-5.8 | FSD FR-6)

**Intent:** Track real portfolio with transactions, see P&L, health grade, rebalancing suggestions.

**Steps to validate:**
- [ ] Portfolio page loads with holdings table
- [ ] "Log Transaction" dialog opens, ticker search works inside it
- [ ] Can add BUY/SELL transactions with date, price, quantity
- [ ] Holdings update with FIFO cost basis, unrealized P&L
- [ ] Portfolio KPI tiles: total value, P&L, health grade
- [ ] Sector allocation donut chart renders
- [ ] Portfolio health sparkline (Spec B wiring)
- [ ] Rebalancing sheet accessible — shows target vs actual allocation
- [ ] Portfolio analytics (QuantStats) — Sortino, max drawdown, alpha
- [ ] Portfolio convergence summary — bullish % across holdings
- [ ] Portfolio forecast (BL + Monte Carlo + CVaR) renders
- [ ] Bulk transaction upload works (CSV)
- [ ] Dividend tracking visible

---

### Journey 5: Dashboard — Daily Intelligence Briefing (PRD 5.5 | FSD FR-17)

**Intent:** 5-zone overview that a busy investor can scan in 5 minutes.

**Steps to validate:**
- [ ] Market Pulse zone: top movers, sector ETFs, market open/closed badge
- [ ] Macro sentiment badge (Spec B wiring)
- [ ] Signals zone: buy-rated stocks, action-required, recommendation accuracy tile
- [ ] Portfolio zone: KPI tiles, health grade, health sparkline (Spec B)
- [ ] Alerts zone: severity-colored alert grid
- [ ] News zone: portfolio-relevant articles with sentiment
- [ ] Clicking any stock navigates to detail page
- [ ] Clicking accuracy tile opens scorecard modal

---

### Journey 6: AI Chat Agent (PRD 5.3 | FSD FR-8)

**Intent:** Conversational AI analyst that answers questions using 25+ tools with evidence.

**Steps to validate:**
- [ ] Chat panel opens from topbar button
- [ ] Agent selector: Stock Analyst / General
- [ ] Type a question → streaming response renders
- [ ] Tool calls show with names and results
- [ ] Evidence section is collapsible with source links
- [ ] Cost/latency shown per query (observability transparency)
- [ ] Session history persists across page navigation
- [ ] Can create new session
- [ ] Decline messages render for out-of-scope queries
- [ ] Suggestions chips work

---

### Journey 7: Alerts & Notifications (PRD 5.19 | FSD FR-9)

**Steps to validate:**
- [ ] Bell icon shows unread count badge
- [ ] Clicking bell opens alert popover
- [ ] Alerts listed with severity coloring
- [ ] Mark as read works (badge count updates)
- [ ] Alert types: trailing stop-loss, concentration, fundamentals deterioration, DQ
- [ ] Clicking an alert navigates to relevant page (stock detail? portfolio?)

---

### Journey 8: Sectors Page (PRD 5.19 | FSD implied)

**Steps to validate:**
- [ ] Sector accordion list renders with sector names + stock count
- [ ] Expanding sector shows stocks in that sector
- [ ] Sector convergence badge shows (Spec B wiring)
- [ ] Correlation matrix heatmap renders
- [ ] Clicking a stock navigates to detail page

---

### Journey 9: Observability — User View (PRD 5.16 | FSD FR-18, FR-19)

**Intent:** Users see their own AI usage costs and query history. Transparency builds trust.

**Steps to validate:**
- [ ] Observability page loads with user-scoped data
- [ ] KPI strip: total queries, total cost, avg latency
- [ ] Query history table with sorting/filtering
- [ ] Click query → detail view with step timeline
- [ ] Langfuse deep-link works (if Langfuse running)
- [ ] Grouped analytics charts render (by model, date, agent_type)
- [ ] Assessment summary visible (golden dataset results)

---

### Journey 10: Admin — Command Center (PRD 5.15 | FSD FR-20)

**Steps to validate:**
- [ ] Page accessible from sidebar (admin only)
- [ ] 5 panels render: System Health, API Traffic, LLM Ops, Pipeline, Forecast Health
- [ ] Each panel with "View Details" drill-down
- [ ] System Health drill-down shows all 5 services with full details
- [ ] API Traffic drill-down shows **per-endpoint error breakdown** (GAP: only shows counts, not errors)
- [ ] LLM Ops drill-down shows per-model cost and cascade log
- [ ] Pipeline drill-down shows run history with task-level status
- [ ] Forecast Health shows backtest accuracy + sentiment coverage
- [ ] Auto-refresh (15s polling) works
- [ ] Degraded badge shows when zones have issues

---

### Journey 11: Admin — Pipeline Control (PRD 5.19 | FSD FR-23)

**Steps to validate:**
- [ ] Page accessible from sidebar (GAP: not in sidebar currently)
- [ ] Task groups listed with task counts
- [ ] "Run All" button triggers pipeline group
- [ ] Progress indicator shows during run
- [ ] Run history shows completed/failed runs with task-level detail
- [ ] Cache controls: pattern clear and full clear work
- [ ] Audit log table shows admin actions with pagination/filtering (Spec C)
- [ ] Individual task trigger works

---

### Journey 12: Admin — Observability Dashboard (FSD FR-28)

**Steps to validate:**
- [ ] Page accessible from sidebar (GAP: not in sidebar currently)
- [ ] 8-zone admin dashboard renders
- [ ] Cost breakdown, error rates, external API health
- [ ] DQ scanner results
- [ ] Error stream with recent errors
- [ ] Pipeline health metrics
- [ ] All zones fetch data and render

---

### Journey 13: Admin — Langfuse Integration (PRD 5.16)

**Steps to validate:**
- [ ] Langfuse accessible at port 3001
- [ ] Traces from agent queries appear in Langfuse
- [ ] Deep-links from observability page open correct trace
- [ ] Cost data syncs between platform and Langfuse

---

### Journey 14: Auth Flows (PRD 5.18 | FSD FR-20)

**Steps to validate:**
- [ ] Login with email/password works
- [ ] Google OAuth login works
- [ ] Registration flow works
- [ ] Email verification banner shows, resend button works
- [ ] Forgot password → reset link → new password flow
- [ ] Account page: change password, delete account
- [ ] Logout clears session
- [ ] Protected routes redirect to login when not authenticated

---

### Journey 15: Recommendations & Scorecard (PRD 5.2, 5.10, 5.11 | FSD FR-4)

**Steps to validate:**
- [ ] Recommendations visible on dashboard signals zone
- [ ] Dedicated recommendations page/view exists (GAP: no page, only dashboard embed)
- [ ] Portfolio-aware reasoning shown ("your allocation is X%, room for Y%")
- [ ] Scorecard accessible — hit rates at 30/90/180d vs SPY
- [ ] Scorecard accessible from stock detail, not just dashboard (GAP: only from dashboard tile)

---

### Journey 16: Navigation & Cross-linking

**Steps to validate:**
- [ ] Sidebar has all pages: Dashboard, Screener, Portfolio, Sectors, Observability, Command Center, Pipelines (admin), Obs Admin (admin), Account
- [ ] Breadcrumbs show correct hierarchy on all pages
- [ ] Stock detail has back navigation to referring page
- [ ] All pages have consistent header/topbar
- [ ] Admin pages properly gated (non-admin redirected)

---

## 4. Known Gaps (Pre-Audit)

These were found during Session 138 and prior sessions. The Playwright audit will verify and extend this list.

| # | Gap | Source | Type | Severity | JIRA |
|---|-----|--------|------|----------|------|
| 1 | External stock add → 404 (no auto-ingest) | FR-2.5, PRD 5.19 | Wiring bug | **CRITICAL** | — |
| 2 | No navigation after stock add | Implicit UX | Missing UX | HIGH | — |
| 3 | Admin Pipelines not in sidebar | FR-23 | Missing nav | **CRITICAL** | KAN-528 P2 |
| 4 | Admin Observability not in sidebar | FR-28 | Missing nav | **CRITICAL** | KAN-528 P2 |
| 5 | CC API Traffic drill-down has no error breakdown | PRD 5.15 | Missing feature | HIGH | KAN-528 P1 |
| 6 | CC System Health drill-down shows same data as panel | PRD 5.15 | Low value | LOW | KAN-528 P4 |
| 7 | CC missing 4 panels (Cache, Chat, Auth, Alerts) | PRD 5.15 | Missing feature | MEDIUM | KAN-523 |
| 8 | CC drill-downs not actionable (no action buttons) | PRD 5.15 | Missing UX | HIGH | KAN-528 P2 |
| 9 | No dedicated recommendations page | FR-4, PRD 5.2 | Missing page | HIGH | — |
| 10 | Scorecard only accessible from dashboard tile | PRD 5.11 | Missing nav | MEDIUM | — |
| 11 | No manual refresh button on stock detail | FR-3.3 | Missing UX | MEDIUM | — |
| 12 | Delta vs full ingest not indicated to user | FR-2.5 | Missing UX | LOW | — |
| 13 | Backtesting Dashboard — no frontend | PRD 5.20 | Missing page | MEDIUM | KAN-521 |
| 14 | LLM Admin Console — no standalone page | PRD 5.4 | Missing page | MEDIUM | KAN-522 |
| 15 | Task Status Polling — needs backend change | FR-23 | Missing feature | LOW | KAN-524 |

---

## 5. Existing JIRA Backlog (Context)

These tickets exist and should be reconciled with audit findings:

| Ticket | Summary | Status |
|--------|---------|--------|
| KAN-504 | UI Overhaul E2E/Integration tests (redefined as this audit) | To Do |
| KAN-521 | Backtesting Dashboard frontend | To Do |
| KAN-522 | LLM Admin Console frontend | To Do |
| KAN-523 | 4 missing CC panels | To Do |
| KAN-524 | Task Status Polling | To Do |
| KAN-528 | CC actionable drill-downs | To Do |
| KAN-429 | JIRA automation bug | To Do |

---

## 6. Execution Plan

### Phase 1: Playwright Intent Audit (1-2 sessions)
Run through all 16 journeys with Playwright. Screenshot every step. Produce a gap table with actual vs expected behavior for every failing step. No code changes — just discovery.

### Phase 2: Critical Wiring Fixes (1-2 sessions)
Fix CRITICAL and HIGH gaps:
- Stock add flow (ingest → watchlist → navigate)
- Admin sidebar navigation (add Pipelines + Obs Admin)
- API Traffic error breakdown in CC drill-down
- Recommendations page
- Stock detail refresh button

### Phase 3: Medium Priority Gaps (1-2 sessions)
- Scorecard multi-entry-point access
- Delta refresh UX indicator
- Bulk transaction CSV validation
- CC action buttons

### Phase 4: Regression Test Suite (1 session)
Convert all Playwright journey steps into permanent E2E test specs. These become the CI guard against future wiring regressions.

---

## 7. Success Criteria

Every journey in Section 3 has:
1. A Playwright screenshot showing it works
2. A passing E2E test that clicks through it
3. Zero gaps between PRD/FSD intent and actual behavior

KAN-400 (UI Overhaul) is only truly done when a user can click through every flow without hitting a dead end, a 404, or a page that only exists via URL.
