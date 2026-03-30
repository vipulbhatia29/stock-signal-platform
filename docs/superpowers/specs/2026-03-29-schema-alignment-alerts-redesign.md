# KAN-227: Schema Alignment + Alerts Redesign

**Epic:** KAN-226 (Phase B.5 — Frontend Catch-Up + Observability Readiness)
**Story:** KAN-227 (BU-1 — Foundation)
**Date:** 2026-03-29
**Status:** Approved

## 1. Overview

Two workstreams in one story:

1. **Schema alignment** — sync `frontend/src/types/api.ts` with all backend Pydantic schemas. Fix 3 mismatched types, add 39 missing types.
2. **Alerts redesign** — extend `InAppAlert` model with `severity`/`title`/`ticker`/`dedup_key` columns, wire divestment alerts into the nightly Celery pipeline, redesign the alert bell popover, add 90-day auto-cleanup for read alerts.

This is the foundation story — every subsequent BU-2 through BU-7 depends on correct TypeScript types.

## 2. Schema Alignment

### 2.1 Mismatched Types (3)

| Frontend Type | Backend Schema | Mismatch |
|---------------|---------------|----------|
| `AlertResponse` | `AlertResponse` | FE has `severity`, `title`, `ticker` that BE doesn't return (fixed by Section 3 migration) |
| `ChatMessage` | `ChatMessageResponse` | FE missing `prompt_tokens`, `completion_tokens`, `latency_ms`, `feedback` |
| `Recommendation` | `RecommendationResponse` | FE missing `suggested_amount` |

### 2.2 Missing Types (39)

| Domain | Types to Add | Count |
|--------|-------------|-------|
| Admin Chat | `AdminChatSessionSummary`, `AdminChatSessionListResponse`, `AdminChatTranscriptResponse`, `AdminChatStatsResponse` | 4 |
| Portfolio Health | `HealthComponent`, `PositionHealth`, `PortfolioHealthResult`, `PortfolioHealthSnapshotResponse` | 4 |
| Market | `IndexPerformance`, `SectorPerformance`, `MarketBriefingResult` | 3 |
| Alerts | `AlertListResponse`, `BatchReadRequest`, `BatchReadResponse`, `UnreadCountResponse` | 4 |
| Intelligence | `NewsItem`, `StockNewsResponse`, `UpgradeDowngrade`, `InsiderTransaction`, `ShortInterest`, `StockIntelligenceResponse` | 6 |
| Health | `MCPToolsStatus`, `DependencyStatus`, `HealthResponse` | 3 |
| LLM Config | `LLMModelConfigResponse`, `LLMModelConfigUpdate`, `TierToggleRequest` | 3 |
| Observability | `KPIResponse`, `QueryRow`, `QueryListResponse`, `StepDetail`, `QueryDetailResponse`, `LangfuseURLResponse`, `AssessmentRunSummary`, `AssessmentHistoryResponse` | 8 |
| Recommend | `StockCandidate`, `RecommendationResult` | 2 |
| Stock | `OHLCResponse` | 1 |
| Auth | `TokenRefreshRequest`, `ChatRequest` | 2 |

### 2.3 Frontend-Only Types (keep as-is)

`TaskStatus`, `RefreshTask`, `StreamEventType`, `StreamEvent`, `EvidenceItem`, `SectorScope`, `ApiError` — these are frontend utilities with no backend equivalent. No changes needed.

### 2.4 Approach

Read each backend schema file in `backend/schemas/`, generate the corresponding TypeScript interface, organize by domain in `types/api.ts`. Preserve existing type ordering conventions (grouped by domain with comment headers).

## 3. Alert Backend — Model Extension + Producers

### 3.1 DB Migration (018)

Add 4 columns to `in_app_alerts` table:

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `severity` | `String(30)` | NOT NULL | `"info"` | `"critical"` \| `"warning"` \| `"info"` — controls UI color |
| `title` | `String(200)` | NOT NULL | `""` | Human-readable alert title (e.g., "Stop-Loss Triggered") |
| `ticker` | `String(10)` | NULL | `None` | Optional stock ticker for navigation |
| `dedup_key` | `String(100)` | NULL | `None` | Composite key for dedup (e.g., `"divestment:stop_loss:TSLA"`, `"signal_flip:downgrade:AAPL"`) |

Add composite index for dedup queries and retention cleanup:
- `ix_in_app_alerts_dedup` on `(user_id, dedup_key, created_at)` — used by dedup lookups
- `ix_in_app_alerts_cleanup` on `(is_read, created_at)` — used by retention DELETE and ORDER BY in list endpoint

Backfill strategy for existing rows: `severity="info"`, `title=""` (frontend falls back to `alert_type` when title is empty), `ticker=None`, `dedup_key=None`.

### 3.2 Schema Updates

Update `AlertResponse` in `backend/schemas/alerts.py`:

```python
class AlertResponse(BaseModel):
    id: uuid.UUID
    alert_type: str
    severity: Literal["critical", "warning", "info"]  # NEW — typed, not bare str
    title: str             # NEW
    ticker: str | None     # NEW
    message: str
    metadata: dict | None = None
    is_read: bool
    created_at: datetime
```

Use `Literal` for `severity` to prevent invalid values at the schema validation layer.

### 3.3 Router Update

Update `backend/routers/alerts.py` — the `get_alerts()` endpoint manually constructs `AlertResponse` (lines 73-83). Add the new fields to the constructor:

```python
AlertResponse(
    id=a.id,
    alert_type=a.alert_type,
    severity=a.severity,       # NEW
    title=a.title,             # NEW
    ticker=a.ticker,           # NEW
    message=a.message,
    metadata=a.metadata_,
    is_read=a.is_read,
    created_at=a.created_at,
)
```

### 3.4 Update Existing Alert Producers

`backend/tasks/alerts.py` already generates 4 alert types but has **no dedup logic**. Update each producer to:
1. Set the new fields (`severity`, `title`, `ticker`, `dedup_key`)
2. Check `dedup_key` before inserting (see §3.6)

| Alert Type | `severity` | `title` | `ticker` | `dedup_key` |
|-----------|-----------|---------|----------|-------------|
| New BUY recommendation | `"info"` | `"New BUY Signal"` | ticker | `"buy:{ticker}"` |
| Signal flip (upgrade) | `"info"` | `"Score Upgrade"` | ticker | `"signal_flip:upgrade:{ticker}"` |
| Signal flip (downgrade) | `"warning"` | `"Score Downgrade"` | ticker | `"signal_flip:downgrade:{ticker}"` |
| Model drift | `"warning"` | `"Forecast Degraded"` | ticker | `"drift:{ticker}"` |
| Pipeline partial failure | `"warning"` | `"Pipeline Issue"` | `None` | `"pipeline:partial"` |
| Pipeline total failure | `"critical"` | `"Pipeline Failed"` | `None` | `"pipeline:total"` |

### 3.5 New Producer: Divestment Alerts

New function in `backend/tasks/alerts.py` called alongside existing producers in Phase 4 of the nightly pipeline.

**Query strategy:** Batch approach (consistent with existing system-wide alert pattern):
1. Fetch all user IDs that have at least one portfolio with positions (single query)
2. For each user: batch-fetch positions, sector allocations, latest signals, and preferences (4 queries per user)
3. Call `check_divestment_rules()` per position (pure function, zero DB calls)
4. Create alerts for triggered rules

**Expected query count:** `1 + (4 × N_users)` — acceptable for nightly batch. If user count exceeds ~100, optimize with JOINs to reduce to `1 + N_users`.

**Alert field mapping:**

| Divestment Rule | `severity` | `title` | `dedup_key` |
|-----------------|-----------|---------|-------------|
| `stop_loss` | `"critical"` | `"Stop-Loss Triggered"` | `"divestment:stop_loss:{ticker}"` |
| `position_concentration` | `"warning"` | `"Concentration Risk"` | `"divestment:position_concentration:{ticker}"` |
| `sector_concentration` | `"warning"` | `"Sector Overweight"` | `"divestment:sector_concentration:{ticker}"` |
| `weak_fundamentals` | `"warning"` | `"Weak Fundamentals"` | `"divestment:weak_fundamentals:{ticker}"` |

Additional fields: `ticker` = position ticker, `message` = from `DivestmentAlert.message`, `metadata` = `{"rule": rule, "value": value, "threshold": threshold, "route": f"/stocks/{ticker}"}`.

### 3.6 Dedup Strategy

Before inserting any alert, check:

```sql
SELECT 1 FROM in_app_alerts
WHERE user_id = :user_id
  AND dedup_key = :dedup_key
  AND created_at > now() - interval '24 hours'
LIMIT 1
```

If a row exists, skip insertion. This uses the `ix_in_app_alerts_dedup` index — fast equality check, no JSONB parsing.

The `dedup_key` column replaces the previous design of querying `metadata->>'rule'` (JSONB), which would require a full scan of the JSON column and cannot be indexed efficiently.

### 3.7 Alert Retention

Add cleanup step to the nightly pipeline (after alert generation):

```sql
DELETE FROM in_app_alerts
WHERE is_read = true
  AND created_at < now() - interval '90 days'
```

**Only deletes read alerts.** Unread alerts older than 90 days are preserved — if a user hasn't logged in for months, they should still see critical unread notifications when they return. Uses `ix_in_app_alerts_cleanup` index.

## 4. Alert Frontend — Popover Redesign

### 4.1 Hook Updates

**`useAlerts()`** — update to parse `AlertListResponse` (which includes `alerts`, `total`, `unread_count`). Return `{ alerts, total, unreadCount, isLoading, isError }`.

**Remove `useUnreadAlertCount()`** — redundant, the list endpoint already returns `unread_count`. The badge reads from `useAlerts().unreadCount` instead.

**`useMarkAlertsRead()`** — keep as-is (PATCH `/alerts/read` with `{ alert_ids }`). Invalidates `["alerts"]` query on success.

### 4.2 Alert Bell Popover

Redesign `frontend/src/components/alert-bell.tsx` to match approved mockup:

**Header:** "Notifications" label + "Mark all read" link (cyan). "Mark all read" shows an undo toast for 5 seconds ("Marked all read. Undo?") — prevents accidental dismissal of important alerts.

**Loading state:** Skeleton placeholder (3 gray shimmer rows) while `useAlerts()` is fetching. Never flash "No notifications" before data arrives.

**Alert items:**
- Blue dot (unread) or hollow dot (read)
- Severity-colored title: critical=`text-loss` (red), warning=`text-warning` (amber), info=`text-cyan`
- **Title fallback:** If `title` is empty (legacy alerts from before migration), display `alert_type` in title-case instead (e.g., `"signal_change"` → `"Signal Change"`)
- Description message (gray)
- Ticker chip at bottom (e.g., "TSLA →") — visible when `ticker` is set
- Read alerts at 60% opacity
- Click behavior:
  - If `ticker` exists: `router.push(/stocks/${ticker})` + mark as read
  - If no `ticker`: mark as read only (no navigation)

**Footer:** "View all notifications →" link (placeholder, no navigation target for now)

**Empty state:** "No notifications" centered text when alerts list is empty, no badge on bell.

**Popover constraints:** Max height 400px, scrollable, shows up to 20 alerts (matches API default `limit=20`).

## 5. Scope Boundaries

### In Scope
- Migration 018 (4 new columns + 2 indexes)
- Schema sync (3 fixes + 39 additions to `types/api.ts`)
- Update 4 existing alert producers with new fields + dedup
- New divestment alert producer with 24h dedup
- 90-day retention cleanup (read alerts only)
- Alert bell popover redesign with loading state + undo toast + title fallback
- Hook updates
- Full test suite (unit + API + frontend)

### Out of Scope
- Dedicated `/alerts` page (future, when more alert types warrant filtering)
- Alert preferences (which types to enable/disable) — future
- Real-time alert creation on portfolio fetch — nightly batch is sufficient
- Push notifications / email alerts
- Additional alert types beyond divestment + existing 4

## 6. Files Changed

### Backend
| File | Change |
|------|--------|
| `backend/models/alert.py` | Add `severity`, `title`, `ticker`, `dedup_key` columns |
| `backend/schemas/alerts.py` | Add fields to `AlertResponse`, use `Literal` for severity |
| `backend/routers/alerts.py` | Add new fields to manual `AlertResponse` constructor |
| `backend/tasks/alerts.py` | Update 4 producers + add divestment producer + dedup logic + retention cleanup |
| `backend/migrations/versions/<autogenerated>_018_alert_severity_title_ticker.py` | New migration (4 columns + 2 indexes) |

### Frontend
| File | Change |
|------|--------|
| `frontend/src/types/api.ts` | Fix 3 mismatches + add 39 types |
| `frontend/src/hooks/use-alerts.ts` | Update `useAlerts()`, remove `useUnreadAlertCount()` |
| `frontend/src/components/alert-bell.tsx` | Full popover redesign (loading state, undo toast, title fallback) |

## 7. Testing

### 7.1 Backend — Unit Tests (mocked)
- Producer logic: given positions/preferences → correct alert objects with right `severity`/`title`/`ticker`/`dedup_key`
- Existing 4 producers: verify they now set `severity`/`title`/`ticker`/`dedup_key`
- Schema serialization: `AlertResponse` includes new fields
- `severity` Literal validation: reject invalid values like `"critcal"` (typo)
- User with no portfolio/watchlist: producer skips gracefully
- Null composite scores / delisted stocks: no crash
- Cascade delete: user deletion removes their alerts
- `dedup_key` format: verify correct composite key for each alert type

### 7.2 Backend — API Tests (testcontainers)
- `GET /alerts` returns `severity`, `title`, `ticker` in response
- `GET /alerts` pagination: `limit`/`offset`, `total`/`unread_count` accurate
- `PATCH /alerts/read` IDOR protection with new columns
- `GET /alerts/unread-count` matches actual count
- Dedup: insert alert with `dedup_key="divestment:stop_loss:TSLA"` → run producer → no duplicate
- Dedup boundary: insert alert from 25h ago with same `dedup_key` → run producer → new alert created
- Multi-user isolation: User A's alerts absent from User B's response
- Concurrent mark-as-read: overlapping IDs → no 500, correct count
- Response shape assertion: JSON shape matches frontend `AlertListResponse` type exactly
- Retention: insert read alert from 91 days ago + unread alert from 91 days ago → cleanup deletes only the read one

### 7.3 Frontend — Component Tests
- `AlertBell` renders correct badge count
- Severity colors: critical=red, warning=amber, info=cyan
- Unread: blue dot. Read: hollow dot + reduced opacity
- Click alert with ticker → `router.push` + `markAsRead` called
- Click alert without ticker → `markAsRead` only, no navigation
- "Mark all read" shows undo toast
- Empty state: no badge, "No notifications" message
- Loading state: skeleton rows shown while fetching
- Title fallback: alert with empty title shows `alert_type` in title-case
- Rapid bell clicks: no duplicate fetches
- Popover scroll with 20 alerts: no viewport overflow
- Long messages: wrapping doesn't break layout

### 7.4 Frontend — Hook Tests
- `useAlerts()` fetches `AlertListResponse`, extracts `alerts` + `unreadCount`
- `useMarkAlertsRead()` invalidates query on success
- Error states: API failure → error returned

### 7.5 Type Safety
- `tsc --noEmit` passes after all type changes — no regressions across all pages

## 8. Breakage Risk Assessment

Changes in this story touch shared contracts. Verified impact:

### Low Risk (contained)
| Change | Consumers | Impact | Fix |
|--------|-----------|--------|-----|
| Remove `useUnreadAlertCount()` | Only `alert-bell.tsx` (verified via grep) | Bell component breaks | Fixed in same task — bell is being rewritten |
| Change `useAlerts()` return shape | Only `alert-bell.tsx` (verified via grep) | Bell component breaks | Fixed in same task — bell is being rewritten |
| Add fields to `ChatMessage` type | Components rendering chat messages | Additive — no breakage expected | `tsc --noEmit` catches if any strict check fails |
| Add `suggested_amount` to `Recommendation` | Components rendering recommendations | Additive — no breakage expected | `tsc --noEmit` catches |

### Zero Risk (purely additive)
| Change | Why safe |
|--------|---------|
| 39 new TypeScript types | No existing code references them — they're for future BU-2 through BU-7 |
| New DB columns with defaults | Existing queries don't SELECT these columns; new code opts in |
| New indexes | Read-only schema change, no query plan regression on existing queries |
| Dedup logic on producers | Existing producers currently have NO dedup — adding it only prevents duplicates, never removes valid alerts |

### Watch Items (verify during implementation)
| Item | Risk | Mitigation |
|------|------|------------|
| Alembic autogenerate may falsely detect TimescaleDB tables | Known gotcha — always review generated migration | Manually write incremental migration if autogenerate rewrites schema |
| `Literal["critical", "warning", "info"]` on schema may reject existing alerts with no severity | Existing rows get `severity="info"` default from migration | Verify migration runs before any API call hits new schema |
| Undo toast for "Mark all read" needs temporary state | React state + setTimeout | If undo fires after component unmounts, guard with cleanup in useEffect |

## 9. Dependencies

- None — this is the foundation story. All BU-2 through BU-7 depend on this.
- Existing nightly Celery pipeline provides the execution context for alert producers.
- `check_divestment_rules()` is an existing pure function — no changes needed to it.
