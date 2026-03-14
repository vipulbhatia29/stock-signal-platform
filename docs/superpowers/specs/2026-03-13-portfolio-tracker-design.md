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

Append-only ledger. Never updated — delete and re-enter if correction needed.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | UUID FK → portfolios.id | CASCADE delete |
| `ticker` | VARCHAR(10) FK → stocks.ticker | Must exist in stocks table |
| `transaction_type` | ENUM('BUY', 'SELL') | |
| `shares` | NUMERIC(12, 4) | Fractional shares supported |
| `price_per_share` | NUMERIC(12, 4) | Price at time of trade |
| `transacted_at` | TIMESTAMPTZ | User-supplied trade date |
| `notes` | TEXT \| NULL | Optional |
| `created_at` | TIMESTAMPTZ | When the record was logged |

**Constraints:**
- `shares > 0` check constraint
- `price_per_share > 0` check constraint
- SELL validated at write time: shares being sold must not exceed current open position

### 2.3 `positions`

Materialized/computed view of current holdings. Recomputed from transactions on every write using FIFO.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `portfolio_id` | UUID FK → portfolios.id | CASCADE delete |
| `ticker` | VARCHAR(10) FK → stocks.ticker | |
| `shares` | NUMERIC(12, 4) | Current open shares |
| `avg_cost_basis` | NUMERIC(12, 4) | FIFO-computed average cost |
| `opened_at` | TIMESTAMPTZ | Date of first BUY |
| `closed_at` | TIMESTAMPTZ \| NULL | Set when shares = 0 (position fully sold) |
| `updated_at` | TIMESTAMPTZ | Last recompute time |

**Design note:** `positions` is a DB table (not a SQL view) so it can be queried efficiently. It is always authoritative — recomputed from the full transaction log whenever a transaction is added or deleted.

---

## 3. FIFO Cost Basis Algorithm

When a transaction is written:

1. Load all BUY transactions for the ticker in `transacted_at` ASC order (the FIFO queue)
2. Load all SELL transactions for the ticker in `transacted_at` ASC order
3. Walk the FIFO queue consuming sells against oldest buys first
4. Remaining BUY lots → `shares` and `avg_cost_basis` (weighted average of remaining lots)
5. Upsert the `positions` row (or set `closed_at` if `shares == 0`)

For SELL validation: before writing, check that open shares ≥ shares being sold. Return HTTP 422 if not.

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
| `DELETE` | `/api/v1/portfolio/transactions/{id}` | Remove a transaction and recompute positions. |
| `GET` | `/api/v1/portfolio/positions` | Current open positions with live P&L. |
| `GET` | `/api/v1/portfolio/summary` | KPI totals + sector allocation breakdown. |

Router mounted in `backend/main.py` at `/api/v1`.

### 4.3 Schemas — `backend/schemas/portfolio.py`

- `TransactionCreate` — request body for POST
- `TransactionResponse` — response for single transaction
- `PositionResponse` — position with P&L fields
- `SectorAllocation` — `{sector: str, value: float, pct: float, over_limit: bool}`
- `PortfolioSummaryResponse` — KPIs + `list[SectorAllocation]`

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
- P&L computation: gain, loss, zero
- SELL validation: insufficient shares raises `ValueError`
- `get_portfolio_summary`: sector grouping and concentration flag

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
