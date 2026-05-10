# Decision Attribution — Link Recommendations to Portfolio Actions, Measure Hit Rate

**Epic:** KAN-569
**Date:** 2026-05-09
**Status:** Design approved

---

## Problem

We generate daily recommendations (BUY/WATCH/AVOID) per ticker per user in `recommendation_snapshots` (nightly pipeline). We track portfolio positions. But there is **zero link** between "what we recommended" and "what the user did." We cannot measure whether our recommendations actually helped.

The existing scorecard (`RecommendationOutcome` + `compute_scorecard()`) measures prediction quality — "did the stock go up after we said BUY?" This module measures **decision quality** — "when the user followed our recommendation, did they make money?"

## Goal

Enable measurement of recommendation quality by tracking:
1. What changed in the user's portfolio (position changelog via CSV diff)
2. Which changes were plausibly triggered by our recommendations (automatic attribution)
3. Whether those attributed trades were profitable (hit rate + alpha)

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Attribution source | CSV diff-on-import only | User imports Fidelity CSVs periodically. No broker API integration. |
| Confirmation UX | Passive auto-match + review dashboard | No friction on import. User reviews/overrides at leisure. |
| Lookback window | 30 days | Part-time investor may let recs marinate. Configurable later. |
| Multiple matches | Score-ranked, all stored, highest = primary | User can override on review dashboard. |
| Non-actions / adherence | Computed on the fly, no storage | Percentages derived from recommendation_snapshots + position_changes at query time. |
| Cold start | Baseline snapshot from existing positions | First import = snapshot zero, no diffs, no false attributions. |
| Multi-user | Fully scoped per user/portfolio | All queries filtered by portfolio_id/user_id. |

---

## Data Model

### `position_snapshots` (TimescaleDB hypertable)

Stores the raw state from each CSV import. One row per ticker per import.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | |
| portfolio_id | UUID | FK → portfolios, NOT NULL | |
| ticker | VARCHAR(20) | FK → stocks, NOT NULL | |
| imported_at | TIMESTAMPTZ | NOT NULL | When this CSV was imported |
| shares | NUMERIC(12,4) | NOT NULL | Quantity from CSV |
| avg_cost_basis | NUMERIC(12,4) | NOT NULL | Cost Basis / Qty |
| market_value | NUMERIC(14,2) | | Mkt Val from CSV |
| current_price | NUMERIC(12,4) | | Price from CSV |
| asset_type | VARCHAR(20) | | "Equity", "ETF", etc. |
| csv_hash | VARCHAR(64) | NOT NULL | SHA-256 of raw CSV content |
| is_baseline | BOOLEAN | DEFAULT false | True for snapshot zero |

**Unique constraint:** `(portfolio_id, ticker, imported_at)`
**Hypertable time column:** `imported_at`
**Indexes:** `(portfolio_id, imported_at DESC)` for "most recent snapshot" queries.

### `position_changes` (regular table)

Computed diffs between consecutive snapshots. One row per ticker that changed.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | |
| portfolio_id | UUID | FK → portfolios, NOT NULL | |
| ticker | VARCHAR(20) | FK → stocks, NOT NULL | |
| detected_at | TIMESTAMPTZ | NOT NULL | When diff was computed |
| snapshot_before_id | UUID | FK → position_snapshots, NULLABLE | NULL for new positions |
| snapshot_after_id | UUID | FK → position_snapshots, NOT NULL | |
| prev_shares | NUMERIC(12,4) | NOT NULL, DEFAULT 0 | |
| new_shares | NUMERIC(12,4) | NOT NULL | |
| delta_shares | NUMERIC(12,4) | NOT NULL | new - prev |
| prev_avg_cost_basis | NUMERIC(12,4) | DEFAULT 0 | |
| new_avg_cost_basis | NUMERIC(12,4) | NOT NULL | |
| implied_action | VARCHAR(10) | NOT NULL | OPEN/ADD/TRIM/CLOSE |
| attribution_status | VARCHAR(10) | DEFAULT 'pending' | pending/matched/confirmed/rejected |

**Indexes:** `(portfolio_id, detected_at DESC)`, `(portfolio_id, ticker)`

**Implied action derivation:**
- prev = 0, new > 0 → OPEN
- prev > 0, new > prev → ADD
- prev > 0, new < prev, new > 0 → TRIM
- prev > 0, new = 0 → CLOSE

### `decision_attributions` (regular table)

Links position changes to candidate recommendations. Multiple candidates per change, one marked primary.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | |
| position_change_id | UUID | FK → position_changes, NOT NULL | |
| rec_generated_at | TIMESTAMPTZ | NOT NULL | Denormalized from recommendation_snapshots |
| rec_ticker | VARCHAR(20) | NOT NULL | Denormalized |
| rec_user_id | UUID | NOT NULL | Denormalized |
| rec_action | VARCHAR(10) | NOT NULL | BUY/SELL/AVOID/HOLD/WATCH |
| rec_confidence | VARCHAR(10) | NOT NULL | HIGH/MEDIUM/LOW |
| match_score | FLOAT | NOT NULL | Combined direction × recency × confidence |
| match_reason | TEXT | NOT NULL | Human-readable explanation |
| is_primary | BOOLEAN | DEFAULT false | Highest-scoring candidate |
| user_verdict | VARCHAR(10) | DEFAULT NULL | confirmed/rejected/null |
| created_at | TIMESTAMPTZ | NOT NULL | |

**Indexes:** `(position_change_id)`, `(is_primary) WHERE is_primary = true`

**No hard FK to recommendation_snapshots** — it's a hypertable with composite PK. We denormalize the key fields (generated_at, ticker, user_id) and display fields (action, confidence) to avoid complex joins.

---

## CSV Validator & Parser

### Fidelity CSV format

```
Row 1: "Positions for account Designated Bene Individual ...063 as of 02:41 AM ET, 2026/04/30"
Row 2: (blank)
Row 3: "Symbol","Description","Qty (Quantity)","Price","Cost Basis","Mkt Val (Market Value)","Asset Type",...
Row 4+: data rows
```

### Required columns (fuzzy matched)

| We need | Matches |
|---|---|
| Symbol | Symbol, Ticker |
| Qty | Qty, Qty (Quantity), Quantity, Shares |
| Price | Price, Last Price, Current Price |
| Cost Basis | Cost Basis, Cost, Total Cost |
| Asset Type | Asset Type, Type (optional — defaults to "Equity") |
| Description | Description, Name (optional) |
| Market Value | Mkt Val, Mkt Val (Market Value), Market Value (optional — derived from Price × Qty) |

Column matching: strip parentheticals, normalize whitespace, case-insensitive.

### Silent fixes (user never sees an error)

| Issue | Fix |
|---|---|
| Extra columns (Theme Qty, Ratings, Reinvest, etc.) | Ignored |
| `$` and `,` in numbers (`$2,989.79`) | Stripped |
| `%` signs (`148.53%`) | Stripped |
| `--` or empty in non-required cells | Default to 0 or null |
| Leading/trailing whitespace | Trimmed |
| Blank rows | Skipped |
| Header not on row 3 | Scan first 10 rows for one containing "Symbol" |
| BOM character (UTF-8-BOM) | Stripped |
| Ticker casing (`aapl`) | Uppercased |
| Summary rows ("Pending Activity", blank Symbol) | Skipped |
| Columns in different order | Matched by name, not position |
| Windows line endings (`\r\n`) | Normalized |
| Quoted vs unquoted fields | CSV parser handles both |
| `Mkt Val` vs `Market Value` vs `Mkt Val (Market Value)` | Fuzzy alias match |
| Cost Basis = `--` or blank | Derive from Price × Qty, warn |

### User-fixable errors

| Issue | Error message |
|---|---|
| File > 512KB | "File too large. Maximum 512KB." |
| No header row found | "Could not find header row. Expected columns: Symbol, Qty, Price, Cost Basis" |
| Missing required column | "Missing column: 'Qty'. Required columns: Symbol, Qty, Price, Cost Basis" |
| Completely wrong format | "Unrecognized file format. Please upload a Fidelity positions CSV." |
| Zero valid rows | "No valid positions found in CSV." |

### Warnings (import proceeds)

| Issue | Warning |
|---|---|
| Unknown ticker | "Row 8: FXAIX not found — skipped. Is this a mutual fund?" |
| Duplicate ticker | "Row 15: AAPL appears twice — first row used" |
| Qty = 0 | Imported (could be closed position) |
| Price = 0 or missing | "Row 12: AAPL has no price — P&L metrics will be incomplete" |

### Dedup protection

`csv_hash` = SHA-256 of raw file content. If same hash exists for this portfolio → reject: "This CSV was already imported on {date}."

### Parser output

```python
@dataclass
class SnapshotRow:
    ticker: str
    description: str
    shares: Decimal
    price: Decimal
    cost_basis: Decimal         # total, not per-share
    market_value: Decimal
    asset_type: str
    avg_cost_basis: Decimal     # computed: cost_basis / shares
```

---

## Snapshot Import Service

**Entry point:** `import_portfolio_snapshot(portfolio_id, user_id, rows, csv_hash, db) → ImportResult`

### Flow

1. **Dedup check** — query `position_snapshots` for this portfolio + csv_hash. If found → reject.

2. **Baseline check** — query `position_snapshots WHERE portfolio_id = X LIMIT 1`. If none exist:
   - If positions already exist in `Position` table (from seed): generate synthetic baseline from current positions, store with `is_baseline=True`.
   - Then store current CSV as second snapshot, compute diffs against baseline.
   - If no positions exist either: store CSV as baseline, `is_baseline=True`, no diffs.

3. **Store snapshot** — bulk insert into `position_snapshots` (one row per ticker).

4. **Auto-create stocks** — call `ensure_stock_exists()` for unknown tickers.

5. **Compute diffs** (skip if baseline) — load previous snapshot (most recent `imported_at` for same portfolio), compare per ticker:
   - In new but not in prev → OPEN (prev_shares=0)
   - In prev but not in new → CLOSE (new_shares=0)
   - Shares increased → ADD
   - Shares decreased → TRIM
   - Shares unchanged → skip

6. **Best-effort Position sync** — upsert Position table to reflect CSV state. This is a convenience sync so the portfolio page shows current holdings. **Position table is NOT the source of truth for attribution** — `position_snapshots` is. See "FIFO Coexistence" below.

7. **Sync Watchlist** — add all imported tickers to user's watchlist (preserves existing `seed_portfolio.py` behavior). Skip tickers already on watchlist.

8. **Run attribution matcher** — for each position_change, find matching recommendations. Non-blocking (same transaction, but no external calls).

9. **Invalidate caches** — call `cache.invalidate_user(user_id)` so frontend hooks (`usePositions`, `usePortfolioSummary`) refetch immediately.

10. **Return ImportResult** — `{imported, warnings, changes_detected, attributions_matched, is_baseline}`

### Edge cases

| Scenario | Handling |
|---|---|
| Same CSV uploaded twice | csv_hash dedup rejects |
| Older CSV uploaded after newer | Diff against most recent by `imported_at`, warn "This CSV appears older than your last import" |
| Ticker in prev but missing from new CSV | CLOSE — shares went to 0 |
| First import with existing seeded positions | Generate synthetic baseline from Position table, then diff |
| CSV has 0 shares for a ticker | Store it. If prev had shares > 0, that's a CLOSE. |

### FIFO coexistence

The Position table has two write paths:

1. **Transaction-driven (FIFO):** `POST /portfolio/transactions` → insert Transaction → `recompute_position()`. Deterministic from immutable ledger.
2. **Snapshot-driven (CSV import):** `POST /portfolio/import-snapshot` → best-effort Position upsert from CSV state.

These are **parallel tracks, not shared**:

- `seed_portfolio.py` is NOT refactored to use the import service (different semantics — it handles user/portfolio creation, price backfill, etc.)
- If a user uses BOTH manual transactions AND CSV imports on the same ticker, the last write wins on the Position table. This is acceptable because:
  - The primary use case is CSV-only users (part-time investors uploading from Fidelity)
  - Attribution uses `position_snapshots` as source of truth, not the Position table
  - Manual transaction users don't need CSV import (they have real-time position tracking)
- The Position table serves the portfolio page display — both paths update it, and the most recent state is always correct for display purposes

---

## Attribution Matcher

### Matching logic

For each position change:

1. **Determine aligned rec actions:**
   - OPEN/ADD → match BUY recommendations
   - TRIM/CLOSE → match SELL/AVOID recommendations

2. **Query candidates:**
   ```sql
   SELECT * FROM recommendation_snapshots
   WHERE user_id = :user_id
     AND ticker = :ticker
     AND generated_at >= :detected_at - INTERVAL '30 days'
     AND generated_at <= :detected_at
     AND action IN (:aligned_actions)
   ```

3. **Score each candidate:**
   ```
   match_score = direction_weight × recency_weight × confidence_weight
   ```
   - **Direction:** 1.0 (always — misaligned filtered in query)
   - **Recency:** linear decay, 1.0 (today) → 0.3 (30 days ago)
   - **Confidence:** HIGH=1.0, MEDIUM=0.7, LOW=0.4

4. **Store all candidates** in `decision_attributions`. Highest score → `is_primary=True`. Set `position_change.attribution_status = 'matched'`.

5. **No candidates** → `attribution_status` stays `'pending'` (independent decision).

### Match reason format

`"BUY HIGH rec on Apr 20 (5 days before ADD), score 0.87"`

### User override logic

- Confirming primary → `user_verdict = 'confirmed'`, `attribution_status = 'confirmed'`
- Rejecting primary → `user_verdict = 'rejected'`, promote next-highest to primary
- Confirming non-primary → swap `is_primary` flags, `attribution_status = 'confirmed'`
- Rejecting all candidates → `attribution_status = 'rejected'`

---

## Hit Rate & Metrics Computation

All metrics computed on the fly — no storage.

### Metrics

```python
@dataclass
class AttributionMetrics:
    # Hit rate
    total_attributed: int
    profitable_count: int
    hit_rate: float | None          # profitable / total (0-1), null if 0 trades

    # Alpha
    avg_return_attributed: float | None
    avg_return_independent: float | None
    alpha: float | None             # attributed - independent

    # Adherence (computed from rec_snapshots + position_changes)
    buy_recs_total: int             # BUY recs in last 90 days
    buy_recs_acted_on: int
    buy_adherence_pct: float | None
    avoid_recs_total: int           # AVOID recs on held positions
    avoid_recs_ignored: int
    avoid_adherence_pct: float | None

    # Breakdown by confidence
    hit_rate_high: float | None
    hit_rate_medium: float | None
    hit_rate_low: float | None
```

### P&L computation

- **OPEN/ADD (buy-side):** `return_pct = (current_price - cost_at_change) / cost_at_change`. Profitable if return > 0.
- **TRIM/CLOSE (sell-side):** position was reduced/exited. Profitable if the stock subsequently dropped (user avoided further loss). Computed as: `return_pct = (price_at_exit - current_price) / price_at_exit`. Profitable if positive (price fell after exit).
- **Closed positions:** use price from CLOSE snapshot as exit price.

### Adherence computation

```sql
-- BUY adherence: of BUY recs in last 90 days, how many had a matching OPEN/ADD within 30 days?
SELECT
    COUNT(*) as total_buy_recs,
    COUNT(pc.id) as acted_on
FROM recommendation_snapshots rs
LEFT JOIN position_changes pc
    ON pc.ticker = rs.ticker
    AND pc.portfolio_id = :portfolio_id
    AND pc.implied_action IN ('OPEN', 'ADD')
    AND pc.detected_at BETWEEN rs.generated_at AND rs.generated_at + INTERVAL '30 days'
WHERE rs.user_id = :user_id
    AND rs.action = 'BUY'
    AND rs.generated_at >= NOW() - INTERVAL '90 days'
```

### Insufficient data handling

| Scenario | Display |
|---|---|
| Zero attributed trades | Metrics null, show "Import more CSVs to see your hit rate" |
| < 5 attributed trades | Show metrics with caveat: "Based on N trades" |
| No AVOID recs | Hide avoid adherence metric |

---

## API Endpoints

### CSV Import

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/portfolio/import-snapshot` | Required | Upload Fidelity CSV |

**Request:** `multipart/form-data` with file field.
**Response (success):**
```json
{
    "imported": 97,
    "warnings": ["Row 15: AAPL appears twice — first row used"],
    "changes_detected": 3,
    "attributions_matched": 2,
    "is_baseline": false
}
```
**Response (validation error):** 422 with list of row-level errors.
**Response (duplicate):** 409 with "This CSV was already imported on {date}."

### Attribution

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/portfolio/attribution/metrics` | Required | Hit rate, alpha, adherence |
| GET | `/api/v1/portfolio/attribution/changes` | Required | Paginated position changes + primary attribution |
| GET | `/api/v1/portfolio/attribution/changes/{id}` | Required | Single change with all candidates |
| PATCH | `/api/v1/portfolio/attribution/{id}/verdict` | Required | Set confirmed/rejected |

**`GET /changes` query params:** `action` (OPEN/ADD/TRIM/CLOSE), `status` (pending/matched/confirmed/rejected), `limit`, `offset`

---

## Frontend

### Portfolio page — Attribution Summary KPIs

New section below existing KPI row. Only renders when ≥ 1 attributed trade exists.

```
┌─────────────────────────────────────────────────────────┐
│  Recommendation Performance                             │
│                                                         │
│  Hit Rate      Alpha       BUY Follow    AVOID Follow   │
│   73%          +2.1%        60%           85%           │
│  (11/15)    vs independent  (9/15 acted) (11/13 heeded)│
│                                                         │
│  [View Details →]                                       │
└─────────────────────────────────────────────────────────┘
```

- Hit Rate: green ≥ 60%, yellow 40-60%, red < 40%
- Alpha: green if positive, red if negative
- Adherence: neutral coloring
- "Based on N trades" caveat when < 5
- "View Details →" links to `/portfolio/attribution`

### Portfolio page — CSV upload button

Alongside existing "Log Transaction":

```
[Log Transaction]  [Import CSV ▲]
```

Import CSV opens dropzone dialog: drag & drop or file picker. Shows validation progress. On success: summary with link to review dashboard. On error: row-level errors.

### Attribution Review Dashboard (`/portfolio/attribution`)

**Section 1: Summary bar** with confidence breakdown.

```
Overall: 73% hit rate    HIGH: 82%  MEDIUM: 64%  LOW: 50%
```

**Section 2: Position changes table**

| Date | Ticker | Action | Attribution | P&L | Status |
|---|---|---|---|---|---|
| May 1 | AAPL | ADD +7 | BUY HIGH (Apr 20) 0.87 | +4.2% | ✓ ✗ |
| May 1 | MSFT | CLOSE | AVOID MED (Apr 15) 0.52 | +1.1% | ✓ ✗ |
| May 1 | NVDA | OPEN +50 | No match — independent | -2.3% | — |

- Click row to expand: shows all candidates, not just primary
- ✓ / ✗ to confirm/reject primary match
- Filters: action, status, date range

**Section 3: Independent decisions** (collapsible) — changes with no matching recommendation.

---

## Implementation Sequence

### PR1: Data Foundation + Import (Steps 1-5)

1. Migration 046: `position_snapshots`, `position_changes`, `decision_attributions` tables + indexes
2. CSV validator + parser (Fidelity format, fuzzy column matching, silent fixes)
3. Snapshot import service (store, baseline bootstrap, diff, compute changes, Position sync, cache invalidation)
4. `POST /portfolio/import-snapshot` endpoint with file upload
5. Pydantic schemas: `ImportResult`, `SnapshotRow`, validation error models

### PR2: Intelligence Layer (Steps 6-8)

6. Attribution matcher service (query candidates, score, rank, store)
7. Attribution review API (list changes, get candidates, set verdict, override logic)
8. Hit rate + adherence computation service + `GET /attribution/metrics` endpoint

### PR3: Frontend (Steps 9-10)

9. Portfolio page: CSV upload dropzone dialog + Attribution Summary KPIs section
10. Attribution Review Dashboard page (`/portfolio/attribution`) with position changes table, candidate expansion, confirm/reject UX

---

## Regression Risks & Mitigations

### HIGH severity

| Risk | Detail | Mitigation |
|---|---|---|
| FIFO conflict | Direct Position upsert from CSV would be overwritten by `recompute_position()` if user later adds a Transaction | Position sync is best-effort display only. Attribution uses `position_snapshots` as source of truth. Two parallel tracks. |
| Frontend stale cache | `usePositions()` has 60s stale time — portfolio page shows old data after import | Import endpoint calls `cache.invalidate_user()`. Frontend response triggers React Query invalidation. |
| FIFO correctness tests | New Position upsert path must not break existing FIFO invariants | Add integration test: import CSV → add manual Transaction → verify FIFO recomputes correctly from Transaction ledger only |

### MEDIUM severity

| Risk | Detail | Mitigation |
|---|---|---|
| Agent tools read stale positions | 5 MCP tools (portfolio_health, recommend_stocks, market_briefing, forecast_tools, portfolio) read Position table | Low risk — imports happen outside agent sessions. No code change needed. |
| Nightly pipeline timing | User imports CSV during nightly run → recommendations based on old state | Acceptable — attribution matcher uses `detected_at` timestamps, not pipeline timestamps |
| `seed_portfolio.py` divergence | Seed script uses direct Position upsert, import service uses snapshot track | Intentional — different semantics. Seed handles user creation, price backfill. Import is user-facing snapshot flow. |
| Position.opened_at mismatch | CSV import doesn't know when position was originally opened | Use import timestamp as `opened_at` for new positions. Existing positions keep their original `opened_at`. |

### Files affected by this feature

| File | Change type | Risk |
|---|---|---|
| `backend/models/portfolio.py` | Add 3 new models | None — additive |
| `backend/schemas/portfolio.py` | Add new Pydantic schemas | None — additive |
| `backend/routers/portfolio.py` | Add new endpoint | LOW — no changes to existing endpoints |
| `backend/services/portfolio/` | New files: `snapshot_import.py`, `csv_parser.py`, `attribution.py`, `hit_rate.py` | None — new files |
| `backend/migrations/versions/` | New migration 046 | LOW — additive tables, no ALTER on existing |
| `frontend/src/hooks/` | New hooks: `useAttributionMetrics`, `usePositionChanges`, `useImportSnapshot` | None — additive |
| `frontend/src/app/(authenticated)/portfolio/` | New components + attribution page | LOW — new sections added to existing page |
| `tests/unit/services/` | New test files for import, attribution, hit rate | None — additive |
| `tests/unit/routers/` | New tests for import endpoint | None — additive |

### Files NOT changed

| File | Why |
|---|---|
| `scripts/seed_portfolio.py` | Different semantics — not refactored |
| `backend/services/portfolio/fifo.py` | FIFO stays transaction-driven, untouched |
| `backend/tasks/recommendations.py` | Reads Position table as before |
| `backend/tasks/portfolio.py` | Snapshot task reads Position table as before |
| `backend/routers/portfolio.py` (existing endpoints) | No changes to transactions, positions, summary, bulk-upload |
| `backend/models/recommendation.py` | Read-only — no schema changes |

---

## Dependencies

- **KAN-568** (portfolio data fix) — MERGED (PR #301). Clean position state exists.
- **`recommendation_snapshots` table** — populated nightly. Sufficient historical data from daily pipeline.
- **`Position` model** — exists, updated by import service (best-effort sync).
- **`ensure_stock_exists()`** — exists, reused for unknown tickers in CSV.
- **Alembic head:** `0ff65ce55dc5` (migration 045). New migration is 046.

## What does NOT change

- `recommendation_snapshots` model or generation pipeline (read-only)
- Existing `POST /portfolio/bulk-upload` endpoint (transaction format, untouched)
- Existing `POST /portfolio/transactions` endpoint (untouched)
- FIFO recomputation logic (`recompute_position()`)
- `seed_portfolio.py` (different semantics, not refactored)
- Forecast track record or evaluation pipeline (separate concern)
- Existing scorecard (prediction quality, complementary to decision quality)
- Nightly pipeline task ordering
