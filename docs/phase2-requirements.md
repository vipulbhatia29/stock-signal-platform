# Phase 2 Requirements Specification — Dashboard + Screener UI

**Date:** 2026-03-07
**Status:** Draft
**Prerequisite:** Phase 1 complete (signal engine, auth, seed scripts, 114 tests)
**Branch:** `feat/dashboard` (to be created off `feat/initial-scaffold`)

---

## 1. User Decisions (from brainstorm)

| Decision | Choice | Impact |
|---|---|---|
| Token storage | httpOnly cookie (Secure, SameSite=Lax) | Backend must set cookies on login/refresh |
| Register page | Self-service (email + password form) | Frontend needs `/register` route |
| Default dashboard view | Major indexes + user's watchlist | Need index membership model in backend |
| Watchlist management | Inline search bar on dashboard (best UX practice) | Autocomplete search component |
| Data ingestion | On-demand from UI; delta fetch for existing tickers | New backend endpoint + delta logic |
| Stock detail | Price chart + signal overlays + signal history (both) | Two chart sections on detail page |
| Timeframe selector | 1M, 3M, 6M, 1Y, 5Y | Price endpoint already supports period param |
| Theme | Dark/light toggle | Tailwind dark mode + theme context |
| Mobile | Deferred — desktop + tablet only | No phone-width breakpoints for now |

---

## 2. Backend Pre-requisites (gaps from Phase 1)

These MUST be built before or alongside the frontend.

### 2.1 httpOnly Cookie Auth

**What:** Modify `/api/v1/auth/login` and `/api/v1/auth/refresh` to set JWT tokens as httpOnly cookies in the response, in addition to (or instead of) returning them in the JSON body.

**Requirements:**
- Set `access_token` as httpOnly, Secure, SameSite=Lax cookie
- Set `refresh_token` as httpOnly, Secure, SameSite=Lax cookie (longer max-age)
- Add a `get_current_user_from_cookie` dependency that reads from cookies
- Support dual-mode: both `Authorization: Bearer` header AND cookie (header takes precedence)
- Add `POST /api/v1/auth/logout` endpoint that clears cookies
- CORS must allow credentials (`allow_credentials=True` + explicit `allow_origins`)

**Files to modify:** `backend/routers/auth.py`, `backend/dependencies.py`, `backend/main.py`

### 2.2 Stock Index Membership

**What:** Add support for major indexes (S&P 500, NASDAQ-100, Dow 30) so the dashboard can group stocks by index.

**Requirements:**
- New model: `StockIndex` (id, name, description) + `StockIndexMembership` (ticker FK, index_id FK)
- Seed scripts for each index (extend `scripts/sync_sp500.py` pattern for NASDAQ-100 and Dow 30)
- Replace `Stock.is_in_universe` boolean with proper index membership
- New endpoints:
  - `GET /api/v1/indexes` — list available indexes with stock counts
  - `GET /api/v1/indexes/{index_id}/stocks` — list stocks in an index with latest price + signal summary
- Alembic migration for new tables

**Files to create/modify:** `backend/models/index.py`, `backend/schemas/index.py`, `backend/routers/indexes.py`, `scripts/sync_indexes.py`, new migration

### 2.3 On-Demand Data Ingestion Endpoint

**What:** When a user searches for a ticker not yet in the system, the UI can trigger data ingestion.

**Requirements:**
- New endpoint: `POST /api/v1/stocks/{ticker}/ingest`
  - Calls `ensure_stock_exists()` to create the Stock record from yfinance
  - Fetches 10Y of OHLCV data (or delta if ticker already has data)
  - Computes signals and stores snapshot
  - Returns 201 with stock info + signal summary
  - Returns 200 if ticker already fully ingested (no-op)
- Delta fetch logic: query `MAX(time)` for ticker from `stock_prices`, fetch only from that date forward
- Update `last_fetched_at` on the Stock record after successful fetch
- Rate-limit this endpoint more aggressively (e.g., 5 requests/minute) — it's expensive
- The existing upsert (ON CONFLICT DO NOTHING) handles idempotency for overlapping data

**Files to modify:** `backend/tools/market_data.py` (add delta fetch), `backend/routers/stocks.py` (new endpoint)

### 2.4 Bulk Signals Endpoint (Screener)

**What:** The screener needs signals for many stocks at once.

**Requirements:**
- New endpoint: `GET /api/v1/stocks/signals/bulk?index={index_id}&limit=100&offset=0`
  - Returns latest signal snapshot for each stock in the specified index
  - Paginated (default limit 50, max 200)
  - Each item includes: ticker, name, sector, composite_score, rsi_signal, rsi_value, macd_signal, sma_signal, bollinger_signal, annualized_return, volatility, sharpe_ratio, computed_at, is_stale
  - Filterable via query params: `rsi_state`, `macd_state`, `sector`, `score_min`, `score_max`
  - Sortable via query params: `sort_by` (any numeric field), `sort_order` (asc/desc)
- Use a single efficient query with `DISTINCT ON (ticker)` + `ORDER BY computed_at DESC`

**Files to modify:** `backend/routers/stocks.py`, `backend/schemas/stock.py`

### 2.5 Signal History Endpoint

**What:** Stock detail page needs historical signal data for charts.

**Requirements:**
- New endpoint: `GET /api/v1/stocks/{ticker}/signals/history?days=90&limit=100`
  - Returns chronological signal snapshots for the ticker
  - Each item: computed_at, composite_score, rsi_value, rsi_signal, macd_value, macd_signal, sma_signal, bollinger_signal
  - Default: last 90 days, max 365 days
- This data powers the signal trend charts on the stock detail page

**Files to modify:** `backend/routers/stocks.py`, `backend/schemas/stock.py`

---

## 3. Frontend Requirements

### 3.1 Project Setup

- Next.js with App Router, TypeScript strict mode
- Tailwind CSS + shadcn/ui component library
- TanStack Query for server state management
- Recharts for all charts
- `lib/api.ts` — centralized fetch wrapper that:
  - Reads CSRF token or uses credentials: "include" for cookie auth
  - Auto-retries on 401 by hitting `/auth/refresh` first
  - Returns typed responses
- Dark/light theme toggle via `next-themes` + Tailwind `darkMode: "class"`
- No phone-width layouts (desktop + tablet only, min-width ~768px)

### 3.2 Pages & Routes

| Route | Page | Auth Required |
|---|---|---|
| `/login` | Login form | No |
| `/register` | Registration form | No |
| `/` | Dashboard (redirects to `/dashboard`) | Yes |
| `/dashboard` | Index cards + watchlist | Yes |
| `/screener` | Filterable stock table | Yes |
| `/stocks/[ticker]` | Stock detail with charts | Yes |

### 3.3 Login Page (`/login`)

**Requirements:**
- Email + password form
- Submit calls `POST /api/v1/auth/login` (sets httpOnly cookie)
- On success: redirect to `/dashboard`
- On error: show inline error message (invalid credentials)
- Link to `/register`
- Centered card layout, works on tablet+

### 3.4 Register Page (`/register`)

**Requirements:**
- Email + password + confirm password form
- Client-side validation: email format, password >= 8 chars, 1 uppercase, 1 digit, passwords match
- Submit calls `POST /api/v1/auth/register`
- On success: redirect to `/login` with success toast
- On error: show inline errors (email taken, validation failures)
- Link to `/login`

### 3.5 Dashboard Page (`/dashboard`)

**Layout:**
```
+--------------------------------------------------+
| Nav: [Dashboard] [Screener]    [Theme] [Logout]  |
+--------------------------------------------------+
| [Search bar: Add ticker to watchlist...]          |
+--------------------------------------------------+
| Major Indexes                                     |
| +----------+ +----------+ +----------+            |
| | S&P 500  | | NASDAQ   | | Dow 30   |           |
| | 503 stocks| | 100 stocks| | 30 stocks|          |
| +----------+ +----------+ +----------+            |
+--------------------------------------------------+
| My Watchlist                    [Sector Filter v] |
| +--------+ +--------+ +--------+ +--------+      |
| | AAPL   | | MSFT   | | GOOGL  | | NVDA   |     |
| | $189.50| | $420.10| | $175.3 | | $890.2 |     |
| | Bullish| | Neutral| | Bearish| | Bullish|     |
| | +12.3% | | +8.1%  | | -2.4%  | | +45.6% |     |
| | 2h ago | | 2h ago | | 2h ago | | 2h ago |     |
| +--------+ +--------+ +--------+ +--------+      |
+--------------------------------------------------+
```

**Requirements:**
- **Search bar** (top): autocomplete search across all stocks in DB. When user selects a ticker:
  - If not in watchlist: add to watchlist + trigger ingestion if no data
  - Show loading state while ingesting
- **Index cards**: clickable cards for S&P 500, NASDAQ-100, Dow 30. Click navigates to `/screener?index={id}`
- **Watchlist section**: grid of stock cards for user's watchlist
  - Each card shows: ticker, current price, sentiment badge (color-coded: green=bullish, yellow=neutral, red=bearish), annualized return %, last updated relative time
  - Click card navigates to `/stocks/{ticker}`
  - Remove button (X) on hover to remove from watchlist
- **Sector filter**: dropdown to filter watchlist cards by sector
- Data fetched via TanStack Query with 5-minute stale time

### 3.6 Screener Page (`/screener`)

**Layout:**
```
+--------------------------------------------------+
| Filters:                                          |
| [Index: All v] [RSI: All v] [MACD: All v]       |
| [Sector: All v] [Score: 0 ----slider---- 10]    |
+--------------------------------------------------+
| Ticker | Sector | RSI | MACD | SMA | Score | ... |
|--------|--------|-----|------|-----|-------|------|
| AAPL   | Tech   | 28  | Bull | Above| 8.2  | ... |  <- green row
| MSFT   | Tech   | 55  | Bear | Above| 5.1  | ... |  <- yellow row
| XOM    | Energy | 72  | Bear | Below| 3.4  | ... |  <- red row
+--------------------------------------------------+
| Showing 1-50 of 503         [< Prev] [Next >]   |
+--------------------------------------------------+
```

**Requirements:**
- **Filters** (top bar): Index selector, RSI state, MACD state, Sector, Composite Score range slider
- **Table columns**: Ticker, Name, Sector, RSI (value + signal), MACD signal, vs SMA 200, Annualized Return, Volatility, Sharpe Ratio, Composite Score
- **Row coloring**: green background tint (score >= 8), yellow (5-7), red (< 5)
- **Sorting**: click any column header to sort asc/desc
- **Pagination**: server-side, 50 rows per page
- **Click row**: navigates to `/stocks/{ticker}`
- Filters applied server-side via query params to `GET /api/v1/stocks/signals/bulk`
- URL state: filters + sort + page reflected in URL query params (shareable/bookmarkable)
- If navigated from dashboard index card, pre-select that index in the filter

### 3.7 Stock Detail Page (`/stocks/[ticker]`)

**Layout:**
```
+--------------------------------------------------+
| <- Back    AAPL - Apple Inc.       [Add to WL]   |
|            Technology | NASDAQ                     |
+--------------------------------------------------+
| Price: $189.50  | Score: 8.2 (BULLISH)           |
| Day Change: +1.2% | Updated: 2h ago              |
+--------------------------------------------------+
| [1M] [3M] [6M] [1Y] [5Y]                        |
| +----------------------------------------------+ |
| |          Price Chart (Recharts)               | |
| |  Line chart with volume bars below           | |
| +----------------------------------------------+ |
+--------------------------------------------------+
| Signal Breakdown                                  |
| +----------+ +----------+ +----------+ +-------+ |
| | RSI: 28  | | MACD:    | | SMA:     | | BB:   | |
| | OVERSOLD | | BULLISH  | | ABOVE200 | | LOWER | |
| +----------+ +----------+ +----------+ +-------+ |
+--------------------------------------------------+
| Signal History (90 days)                          |
| +----------------------------------------------+ |
| |  Composite score line chart over time         | |
| |  RSI line chart (with 30/70 threshold lines) | |
| +----------------------------------------------+ |
+--------------------------------------------------+
| Risk & Return                                     |
| Ann. Return: 12.3% | Volatility: 22.1%          |
| Sharpe Ratio: 0.54                               |
+--------------------------------------------------+
```

**Requirements:**
- **Header**: ticker, company name, sector, exchange, add/remove watchlist button
- **Price summary**: current price, day change %, composite score with badge, last updated
- **Price chart** (Recharts): line chart with timeframe selector (1M/3M/6M/1Y/5Y)
  - Uses `GET /api/v1/stocks/{ticker}/prices?period={period}`
  - Volume bars as secondary axis
- **Signal breakdown cards**: current RSI, MACD, SMA, Bollinger values with color-coded labels
- **Signal history chart**: composite score over time + RSI over time (dual-axis or stacked)
  - Uses `GET /api/v1/stocks/{ticker}/signals/history?days=90`
  - RSI chart includes 30/70 threshold lines
- **Risk & return section**: annualized return, volatility, Sharpe ratio
- If ticker has no data: show "Ingest Data" button that calls `POST /api/v1/stocks/{ticker}/ingest` with loading spinner

### 3.8 Navigation & Auth Guard

**Requirements:**
- Persistent top nav bar: Dashboard, Screener links + theme toggle + logout button
- Auth guard middleware: check for valid cookie on protected routes
  - If no cookie / cookie expired: redirect to `/login`
  - On 401 from any API call: attempt refresh, if refresh fails redirect to `/login`
- Logout: calls `POST /api/v1/auth/logout` (clears cookies) + redirect to `/login`

---

## 4. Acceptance Criteria

### Functional
- [ ] Can register a new account from `/register`
- [ ] Can log in and be redirected to dashboard
- [ ] Dashboard shows index cards for S&P 500, NASDAQ-100, Dow 30
- [ ] Dashboard shows user's watchlist with live signal data
- [ ] Can search and add a ticker to watchlist from dashboard
- [ ] Adding a new ticker triggers data ingestion if not in system
- [ ] Can filter watchlist by sector
- [ ] Screener displays all stocks in an index with signal data
- [ ] Screener filters (RSI, MACD, sector, score range) work correctly
- [ ] Screener sorts by any column
- [ ] Screener rows are color-coded by composite score
- [ ] Stock detail shows price chart with timeframe selector
- [ ] Stock detail shows signal breakdown cards
- [ ] Stock detail shows signal history chart
- [ ] Dark/light theme toggle works and persists
- [ ] Logout clears auth state and redirects to login

### Non-Functional
- [ ] Dashboard loads in < 2 seconds with pre-computed data
- [ ] Screener handles 500 stocks without performance degradation
- [ ] All pages responsive at tablet width (768px+)
- [ ] Auth cookies are httpOnly, Secure, SameSite=Lax
- [ ] No `any` types in TypeScript code
- [ ] All API calls go through centralized fetch wrapper

### Testing
- [ ] Backend: new endpoints have auth + happy path + error path tests
- [ ] Frontend: key components have unit tests (vitest)
- [ ] E2E: login -> dashboard -> screener -> stock detail flow works

---

## 5. Out of Scope (Phase 2)

- Portfolio tracking (Phase 3)
- AI chatbot (Phase 4)
- Recommendation generation from UI (Phase 3)
- Mobile phone layouts (deferred)
- Real-time price updates / WebSocket (future)
- Export / download functionality

---

## 6. Implementation Order

### Backend Pre-requisites (build first)
1. httpOnly cookie auth + logout endpoint
2. Stock index membership model + migration + seed scripts
3. On-demand data ingestion endpoint (with delta fetch)
4. Bulk signals endpoint (for screener)
5. Signal history endpoint

### Frontend (after backend endpoints exist)
1. Next.js project setup (App Router, Tailwind, shadcn/ui, TanStack Query, theme)
2. `lib/api.ts` fetch wrapper with cookie auth
3. Login + Register pages
4. Auth guard middleware
5. Dashboard layout + nav
6. Index cards component
7. Watchlist cards + search bar
8. Screener page (table, filters, sorting, pagination)
9. Stock detail page (price chart, signal cards, signal history chart)
10. Dark/light theme toggle
11. Polish: loading states, error states, empty states
