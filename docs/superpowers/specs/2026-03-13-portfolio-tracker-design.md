# Portfolio Tracker — Design Spec

**Date:** 2026-03-13
**Branch:** `feat/phase-3-portfolio`
**Status:** Approved — ready for implementation planning

---

## 1. Scope

### In scope (this sprint)

- **Transaction log** — manual BUY/SELL entry (ticker, shares, price per share, date, optional notes)
- **Positions + P&L** — current holdings computed via FIFO cost basis; unrealized gain/loss, % return, market value
- **Allocation view** — sector % and per-stock % of portfolio total; concentration warning if any sector exceeds 30%

### Explicitly deferred

| Feature | Reason |
|---|---|
| Portfolio value history chart | Requires Celery daily snapshots — extra infra overhead |
| Dividend tracking | Separate data model; not core to P&L for now |
| Divestment alerts (stop-loss, concentration) | Depends on alert engine — Phase 3.5 |
| Portfolio-aware recommendations | Upgrade to recommendations engine — Phase 3.5 |
| Rebalancing suggestions | Depends on alerts + recommendations |
| Schwab OAuth sync | Phase 4 dedicated feature |
| Multi-account support (Fidelity, IRA etc.) | Phase 4 — single Schwab taxable account for now |

---

## 2. Data Model

### 2.1 `portfolios`

One row per user. Created automatically on first use (or on registration).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → users.id | CASCADE delete |
| `name` | VARCHAR(100) | Default: "My Portfolio" |
| `description` | TEXT \| NULL | Optional user note |
| `created_at` | TIMESTAMPTZ | Auto |
| `updated_at` | TIMESTAMPTZ | Auto |

### 2.2 `transactions`

Append-only ledger. Never updated — delete and re-enter if correction needed. Uses `UUIDPrimaryKeyMixin` only (no `TimestampMixin` — `updated_at` is meaningless on an immutable ledger row; `created_at` is declared explicitly).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | UUID FK → portfolios.id | CASCADE delete |
| `ticker` | VARCHAR(10) FK → stocks.ticker | Must exist in stocks table — see §4.2 for FK error handling |
| `transaction_type` | ENUM('BUY', 'SELL') | |
| `shares` | NUMERIC(12, 4) | Fractional shares supported |
| `price_per_share` | NUMERIC(12, 4) | Price at time of trade |
| `transacted_at` | TIMESTAMPTZ | User-supplied trade date |
| `notes` | TEXT \| NULL | Optional |
| `created_at` | TIMESTAMPTZ | When the record was logged (auto) |

**Constraints:**
- `shares > 0` check constraint
- `price_per_share > 0` check constraint
- SELL validated at write time: shares being sold must not exceed current open position

### 2.3 `positions`

Materialized/computed view of current holdings. Recomputed from transactions on every write using FIFO. Uses `UUIDPrimaryKeyMixin` + `TimestampMixin` (adds `created_at` + `updated_at`).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | UUID FK → portfolios.id | CASCADE delete |
| `ticker` | VARCHAR(10) FK → stocks.ticker | |
| `shares` | NUMERIC(12, 4) | Current open shares (0 when closed) |
| `avg_cost_basis` | NUMERIC(12, 4) | Weighted average cost of *remaining* FIFO lots (display only — not tax-lot ACB) |
| `opened_at` | TIMESTAMPTZ | Date of first BUY — **never overwritten on upsert** (see §3) |
| `closed_at` | TIMESTAMPTZ \| NULL | Set when shares = 0 (position fully sold) |
| `created_at` | TIMESTAMPTZ | Auto via TimestampMixin |
| `updated_at` | TIMESTAMPTZ | Auto-updated on every FIFO recompute via TimestampMixin |

**Design note:** `positions` is a DB table (not a SQL view) so it can be queried efficiently. It is always authoritative — recomputed from the full transaction log whenever a transaction is added or deleted.

---

## 3. FIFO Cost Basis Algorithm

### On transaction write (BUY or SELL)

1. Load all transactions for the ticker in `transacted_at` ASC order (BUYs and SELLs interleaved)
2. Walk chronologically, maintaining a deque of BUY lots `[(shares, price), ...]`
3. On each SELL: consume from the front of the deque (FIFO); if the deque runs out before the sell is satisfied → raise `ValueError("Insufficient shares")` (router returns 422)
4. After the full walk: remaining lots in deque → compute `shares` (sum) and `avg_cost_basis` (weighted average)
5. Upsert the `positions` row:
   - `INSERT ... ON CONFLICT (portfolio_id, ticker) DO UPDATE SET shares=..., avg_cost_basis=..., closed_at=..., updated_at=now()`
   - **`opened_at` is explicitly excluded from the UPDATE clause** — it preserves the original first-BUY date on every recompute
   - Set `closed_at = transacted_at of final SELL` if remaining `shares == 0`; otherwise `closed_at = NULL`

### On transaction delete (DELETE `/api/v1/portfolio/transactions/{id}`)

**Pre-delete validation:** Simulate removal by running the FIFO walk over all remaining transactions (excluding the target). If the walk raises `ValueError` at any point (a SELL becomes short after removing a BUY), return HTTP 422 with message `"Cannot delete: removing this transaction would leave a later SELL without sufficient shares"`. Only proceed with DELETE if the simulation succeeds.

After deleting, run a full FIFO recompute and upsert positions as above.

### Edge cases

| Case | Behaviour |
|---|---|
| SELL exact remaining shares | `closed_at` set, `shares = 0` — position marked closed |
| BUY entered with a past `transacted_at` | FIFO walk re-runs from scratch in chronological order; downstream SELLs may now match different lots |
| Ticker with `NULL` sector | Bucketed as `"Unknown"` in sector allocation breakdown |
| Empty portfolio (no transactions) | `GET /positions` returns `[]`; `GET /summary` returns all KPIs as 0 |

---

## 4. Backend

### 4.1 Tool — `backend/tools/portfolio.py`

Functions:
- `get_or_create_portfolio(user_id, db)` → `Portfolio` — auto-creates on first call
- `compute_positions(portfolio_id, db)` → `list[Position]` — runs FIFO and upserts positions table
- `get_positions_with_pnl(portfolio_id, db)` → `list[PositionWithPnL]` — joins latest price from `stock_prices`, computes unrealized P&L and market value
- `get_portfolio_summary(portfolio_id, db)` → `PortfolioSummary` — aggregates total value, cost basis, P&L, sector breakdown
- `validate_sell(portfolio_id, ticker, shares, db)` → raises `ValueError` if insufficient shares

### 4.2 Router — `backend/routers/portfolio.py`

All endpoints require JWT auth (`get_current_user` dependency).

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/portfolio/transactions` | Log a BUY or SELL. Recomputes positions. Returns created transaction. |
| `GET` | `/api/v1/portfolio/transactions` | Full transaction history, sorted `transacted_at DESC`. Supports `?ticker=AAPL` filter. |
| `DELETE` | `/api/v1/portfolio/transactions/{id}` | Simulate removal; reject 422 if it would invalidate a SELL. Then delete + recompute. |
| `GET` | `/api/v1/portfolio/positions` | Current open positions with live P&L. |
| `GET` | `/api/v1/portfolio/summary` | KPI totals + sector allocation breakdown. |

**Ticker FK error handling:** If the user submits a ticker not in the `stocks` table, the router catches the FK integrity error and returns HTTP 422 with `{"detail": "Ticker 'XYZ' not found. Add it to your watchlist first to ingest it."}` — do not let the DB error bubble as a 500.

Router mounted in `backend/main.py` at `/api/v1`.

### 4.3 Schemas — `backend/schemas/portfolio.py`

- `TransactionCreate` — request body for POST
- `TransactionResponse` — response for single transaction
- `PositionResponse` — position with P&L fields: `ticker`, `shares`, `avg_cost_basis`, `current_price`, `market_value`, `unrealized_pnl`, `unrealized_pnl_pct`, `allocation_pct`
- `SectorAllocation` — `{sector: str, market_value: float, pct: float, over_limit: bool}`
- `PortfolioSummaryResponse` — fields: `total_value: float`, `total_cost_basis: float`, `unrealized_pnl: float`, `unrealized_pnl_pct: float`, `position_count: int`, `sectors: list[SectorAllocation]`

### 4.4 Migration

Alembic migration `005_portfolio_tables` covering:
- CREATE `portfolios`
- CREATE `transactions` (with check constraints)
- CREATE `positions`
- Index on `transactions(portfolio_id, ticker, transacted_at)`
- Index on `positions(portfolio_id, ticker)`

---

## 5. Frontend

### 5.1 Route

New page: `frontend/src/app/(authenticated)/portfolio/page.tsx`

Added to nav bar alongside Dashboard and Screener.

### 5.2 Layout (Layout A — approved)

```
┌─────────────────────────────────────────────────────┐
│  KPI Row: Total Value | Cost Basis | P&L | Positions │
├──────────────────────────────┬──────────────────────┤
│  Positions Table (3fr)       │  Allocation (2fr)    │
│  Ticker | Shares | Avg Cost  │  Recharts PieChart   │
│  Current | Value | P&L | %   │  Sector legend       │
│                              │  ⚠️ >30% warning     │
├──────────────────────────────┴──────────────────────┤
│  [+ Log Transaction]  (button, top-right of section) │
└─────────────────────────────────────────────────────┘
```

### 5.3 "Log Transaction" Dialog

shadcn `Dialog` containing a form:
- Ticker search (reuses existing search component / autocomplete from stocks in DB)
- Transaction type: BUY | SELL (radio or segmented control)
- Shares (number input, allows decimals)
- Price per share (number input)
- Date (date picker, defaults to today)
- Notes (optional textarea)
- Submit → `useMutation` → `POST /api/v1/portfolio/transactions` → invalidate positions + summary queries

### 5.4 Data Fetching

- `useQuery(['portfolio', 'positions'])` → `GET /api/v1/portfolio/positions`
- `useQuery(['portfolio', 'summary'])` → `GET /api/v1/portfolio/summary`
- `useQuery(['portfolio', 'transactions'])` → `GET /api/v1/portfolio/transactions` (transactions history panel, collapsed by default)
- All via TanStack Query v5; mutations invalidate relevant queries on success

### 5.5 New TypeScript Types (`frontend/src/types/api.ts`)

- `Transaction`, `TransactionCreate`
- `Position` (with P&L fields)
- `SectorAllocation`
- `PortfolioSummary`

---

## 6. Testing

### Unit tests — `tests/unit/test_portfolio.py`

- FIFO cost basis: single BUY, multiple BUYs, partial SELL, full SELL, multiple tickers
- FIFO: SELL exact remaining shares → `closed_at` set, `shares = 0`
- FIFO: BUY entered with past `transacted_at` after a SELL → walk re-orders correctly
- FIFO: two tickers, SELL overdraft on one but not the other (isolation)
- DELETE pre-validation: removing BUY that underlies a SELL → raises `ValueError`
- P&L computation: gain, loss, zero
- SELL validation: insufficient shares raises `ValueError`
- `get_portfolio_summary`: sector grouping, concentration flag, NULL sector → "Unknown"

### API tests — `tests/api/test_portfolio.py`

For each endpoint:
- **Auth:** 401 when no token
- **Happy path:** expected response shape and values
- **Error path:** 422 for invalid input, 422 for oversell

### Factories — `tests/conftest.py`

- `PortfolioFactory`
- `TransactionFactory` (with `transaction_type`, `shares`, `price_per_share`, `transacted_at`)

---

## 7. What's NOT changing

- `backend/tools/recommendations.py` — not portfolio-aware yet (Phase 3.5)
- `backend/tools/signals.py` — unchanged
- Composite score weights — still 100% technical (Phase 3.5 introduces fundamental blend)
- Watchlist — unchanged

---

## 8. Decisions Log

| Decision | Rationale |
|---|---|
| Single portfolio per user | User has one Schwab taxable account; multi-account is Phase 4 |
| `positions` as DB table, not SQL view | Queryable, indexable, avoids re-running FIFO on every read |
| FIFO recomputed on every transaction write | Simplest correct approach; position count is small for a personal investor |
| SELL validation at write time | Prevents invalid state; 422 with clear message |
| Manual entry only | Schwab OAuth deferred; CSV import not needed when entry count is manageable |
| Fractional shares (`NUMERIC(12,4)`) | Schwab supports fractional shares |
| No `Portfolio` model required for single-user | Still creating it — makes multi-account extension trivial later |
