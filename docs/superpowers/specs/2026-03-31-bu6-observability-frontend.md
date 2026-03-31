# BU-6: Observability Frontend — Requirements Specification

**Date:** 2026-03-31
**JIRA:** KAN-232 (under Epic KAN-226)
**Predecessor:** BU-5 (KAN-231, PR #152) — backend API complete
**Status:** Spec reviewed (3-expert panel), all findings resolved

---

## 1. Goal

Build the frontend observability page that lets users see how the AI agent works on their behalf — queries made, tools used, costs incurred, latency, quality scores. This is a **SaaS differentiator**: users see how their subscription money is working.

NOT internal admin tooling. Regular users see their own data; admins see aggregate/all-user data on the same page via conditional rendering.

## 2. User Stories

### US-0: User Profile Endpoint (Backend Pre-requisite)
**As a** frontend developer, **I need** a `/auth/me` endpoint that returns the current user's profile including role **so that** the frontend can conditionally render admin-only sections.

**Acceptance Criteria:**
- `GET /api/v1/auth/me` → `{ id, email, role, is_active }` (JWT auth required)
- `useCurrentUser()` hook in frontend, called once on auth success, cached
- Auth context extended: `user: { id, email, role, isAdmin } | null`
- No new migration — reads existing `User.role` field

**Why:** The current `useAuth()` context has no role information. JWT doesn't embed role. No `/me` endpoint exists. Without this, role-aware rendering is impossible.

### US-1: KPI Health Check
**As a** user, **I want to** see top-level metrics (queries today, avg latency, avg cost, pass rate, fallback rate) **so that** I know the AI agent is working correctly.

**Acceptance Criteria:**
- 5 KPI cards in a horizontal strip at the top of the page, using `StatTile` component
- Each card: uppercase 9.5px label (text-subtle), large mono value (font-mono font-bold), accent gradient top border
- Formatting:
  - queries_today → integer, accent: cyan
  - avg_latency_ms → `formatDuration()` (new), accent: cyan
  - avg_cost_per_query → `formatMicroCurrency()` (new, 4 decimal), accent: cyan
  - pass_rate → `formatPercent()`, accent: gain (≥80%) / warning (50-80%) / loss (<50%), null → "—"
  - fallback_rate_pct → `formatPercent()`, accent: gain (<5%) / warning (5-15%) / loss (>15%)
- Loading skeleton matching `StatTile` dimensions
- Responsive: 5-col on desktop, 2-col + 3-col on tablet, stack on mobile

### US-2: Query History Table
**As a** user, **I want to** see a paginated, sortable, filterable list of my AI queries **so that** I can trace what the agent did for each question I asked.

**Acceptance Criteria:**
- Table columns: timestamp, query text (truncated), agent type, tools used (pill badges, cap at 3 + "+N"), LLM calls count, total cost, duration, status
- Score column: **visible only for admin users** (most rows will be null for regular users)
- Sort by: timestamp (default desc), total_cost_usd, duration_ms, llm_calls, score (admin only)
- Filter by: status (completed/error/declined/timeout dropdown), cost range (min/max inputs)
- Pagination: page size 25, page controls at bottom
- Status shown as colored badge:
  - completed → `bg-gdim text-gain` (green)
  - error → `bg-ldim text-loss` (red)
  - declined → `bg-wdim text-warning` (yellow)
  - timeout → `bg-muted text-muted-foreground` (grey)
- Tool pills: `bg-cdim text-cyan` rounded-full, max 3 visible + "+N" overflow badge
- Row click → expand detail (US-3)
- Row hover: `bg-hov`
- Table header: `bg-card2` sticky
- Sort icons: ChevronUp/Down matching screener pattern
- Loading: 8 skeleton rows (`<Skeleton className="h-10 w-full" />`)
- Empty state: "No queries yet — try asking the AI agent a question!" with cyan CTA button → opens chat panel
- All table state persisted in URL params: `?page=1&sort=timestamp&order=desc&status=error&cost_min=0.01`

### US-3: Query Detail Expansion
**As a** user, **I want to** expand a query row to see the step-by-step execution trace **so that** I understand exactly what the agent did.

**Acceptance Criteria:**
- Click row → inline accordion expansion below the row (new pattern)
- Implementation: `<tr>` with `colSpan={totalColumns}` containing detail component
- Animation: CSS `max-height` transition (0 → auto, 300ms ease)
- Only one row expanded at a time (clicking another row collapses the previous)
- Keyboard: Enter/Space on focused row toggles expansion
- `aria-expanded` on trigger row
- Fetched on-demand: `useQuery` with `enabled: !!expandedQueryId` (not pre-loaded)
- Shows ordered list of steps, each as a horizontal card:
  - Step number (circle badge)
  - Action name (mono font)
  - Type tag as colored pill: llm → `bg-purple-500/15 text-purple-400`, db → `bg-cdim text-cyan`, external → `bg-wdim text-warning`
  - Input summary (text-muted-foreground, truncated)
  - Output summary (text-muted-foreground, truncated)
  - Latency: `formatDuration()`
  - Cost: `formatMicroCurrency()` (only for LLM steps)
  - Cache hit: small "cached" badge (`bg-gdim text-gain`)
- Full query text shown above steps (not truncated)
- "View in Langfuse" button if `langfuse_trace_url` is present → `target="_blank" rel="noopener"`
- Collapse on second click

### US-4: Grouped Analytics Charts
**As a** user, **I want to** see trends and breakdowns of my query usage **so that** I understand cost patterns and can optimize my usage.

**Acceptance Criteria:**
- Dimension selector as **tabs** (matching screener TAB_COLUMNS pattern):
  ```
  Over Time | By Model | By Provider | By Agent | By Status | By Tool
  ```
- Admin-only tabs (conditionally rendered via `isAdmin`): By User, By Intent
- Date dimension (default):
  - Line chart (Recharts ComposedChart) with dual Y-axis
  - Left axis: total_cost_usd (cyan line + area fill)
  - Right axis: avg_latency_ms (purple line)
  - Bucket selector pills: Day | Week | Month (below chart)
  - X-axis: `formatChartDate()`
- Categorical dimensions (model, provider, agent_type, status, tier):
  - Bar chart (BarChart) showing query_count bars + total_cost overlay
  - Colors from `useChartColors()` palette
- tool_name:
  - Horizontal bar chart (sorted by usage frequency desc)
- Date range quick selectors: 7d / 30d / 90d pill buttons (above chart, right-aligned)
- All charts use `useChartColors()` + `CHART_STYLE` for grid/axis styling
- Chart tooltip: `bg-card border-border` matching existing ChartTooltip pattern
- Loading: chart-sized skeleton placeholder
- Empty state: "Not enough data to show trends" with muted icon

### US-5: Assessment Quality Section
**As a** user, **I want to** see how well the AI agent performs on quality benchmarks **so that** I trust the recommendations it gives me.

**Acceptance Criteria:**
- Framed as **platform quality** (not per-user): "We regularly test AI quality against benchmarks"
- Latest assessment run shown to ALL users (public endpoint):
  - Large pass_rate number with gain/loss accent (StatTile pattern)
  - Supporting metrics: total_queries tested, total_cost, "Last tested: {relative time}"
  - Pass rate coloring: gain (≥80%), warning (50-80%), loss (<50%)
- Admin-only: assessment history table below (trigger, pass_rate, total_queries, cost, dates)
  - Rendered only when `user.isAdmin === true`
- If no assessment data: "Quality benchmarks coming soon" neutral message (text-muted-foreground)

### US-6: Navigation
**As a** user, **I want to** access the observability page from the sidebar **so that** I can quickly check AI performance.

**Acceptance Criteria:**
- New entry in `NAV_ITEMS` array in `sidebar-nav.tsx`:
  ```tsx
  { href: "/observability", label: "Observability", icon: Activity }
  ```
- Position: after Sectors (index 4)
- Active state: `pathname.startsWith("/observability")` → cyan icon + `bg-cdim` + left accent bar
- Import `Activity` from `lucide-react`

## 3. Non-Functional Requirements

### NFR-1: Performance
- Page should render meaningful content within 1s on 4G
- KPI strip loads independently (no blocking on table data)
- Charts load independently (no blocking on table data)
- Query detail fetched on-demand with `enabled: !!expandedQueryId`
- Progressive loading order: KPIs → charts + table in parallel → detail on click

### NFR-2: Caching (TanStack Query stale times)
- KPIs: 60s
- Query list: 60s (was 30s — bumped because aggregation queries are expensive)
- Grouped analytics: 120s
- Assessment: 300s
- Query detail: Infinity (immutable once created)
- Current user profile: Infinity (role doesn't change during session)

### NFR-3: Design Consistency
- All components use existing navy design system tokens
- Cards: `bg-card` / `bg-card2` backgrounds, `border-border`, `rounded-[var(--radius)]`
- Text: `text-foreground` / `text-muted-foreground` / `text-subtle`
- Labels: `text-[9.5px] font-semibold uppercase tracking-[0.1em] text-subtle`
- Values: `font-mono font-bold` (sizes vary: 16px-20px)
- Borders: `border-border` standard, `border-[var(--bhi)]` for emphasis/hover
- Accent: cyan (`--cyan`), dim variants (`--cdim`)
- Semantic: `--gain`, `--loss`, `--warning` for status colors
- Dim backgrounds: `bg-gdim`, `bg-ldim`, `bg-wdim`, `bg-cdim` for badges
- Charts: `useChartColors()` + `CHART_STYLE` for all Recharts
- Fonts: Sora for UI, JetBrains Mono for values/code
- Animations: `PageTransition` wrapper, `StaggerGroup`/`StaggerItem` for KPI cards
- No hardcoded color values anywhere

### NFR-4: Accessibility
- Table sortable columns: `aria-sort="ascending"` / `"descending"` / `"none"`
- Expandable rows: `aria-expanded="true"` / `"false"`, `role="button"`, `tabIndex={0}`
- Keyboard: Enter/Space toggles row expansion
- Chart data available as underlying table (grouped response is structured data)
- Focus visible indicators on all interactive elements

### NFR-5: Role-Aware Rendering
- Single page, single route (`/observability`)
- `useCurrentUser()` hook provides `isAdmin` boolean
- Admin-only sections conditionally rendered (not hidden via CSS — not in DOM at all)
- No 403 errors visible to users — admin sections simply don't render
- Admin-only elements: assessment history table, score column, user/intent_category chart tabs

### NFR-6: URL State Persistence
All filter/sort/view state in URL search params for shareability:
- `page` (int, default 1)
- `sort` (string, default "timestamp")
- `order` ("asc" | "desc", default "desc")
- `status` (string, optional)
- `cost_min` (float, optional)
- `cost_max` (float, optional)
- `dim` (string, default "date") — active chart dimension
- `bucket` ("day" | "week" | "month", default "day")
- `range` ("7d" | "30d" | "90d", default "30d") — date range

## 4. Backend API Contract (from BU-5)

All endpoints at `/api/v1/observability/`, JWT auth required.

| Endpoint | Method | Response | Notes |
|---|---|---|---|
| `/auth/me` | GET | UserProfile | **NEW** — returns id, email, role, is_active |
| `/kpis` | GET | KPIResponse | User-scoped |
| `/queries` | GET | QueryListResponse | Paginated, 5-col sort, status/cost filter |
| `/queries/grouped` | GET | GroupedResponse | 9 dimensions, date bucketing |
| `/queries/{query_id}` | GET | QueryDetailResponse | Steps + Langfuse URL |
| `/queries/{query_id}/langfuse-url` | GET | LangfuseURLResponse | Separate URL fetch |
| `/assessment/latest` | GET | AssessmentRunSummary | Public |
| `/assessment/history` | GET | AssessmentHistoryResponse | Admin-only (403 for non-admins) |

### Enums
- SortByEnum: timestamp, total_cost_usd, duration_ms, llm_calls, score
- SortOrderEnum: asc, desc
- StatusFilterEnum: completed, error, declined, timeout
- GroupByEnum: agent_type, date, model, status, provider, tier, tool_name, user, intent_category
- DateBucketEnum: day, week, month

## 5. TypeScript Types Needed

```typescript
// User profile (NEW)
interface UserProfile {
  id: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
}

// KPIs
interface KPIResponse {
  queries_today: number;
  avg_latency_ms: number;
  avg_cost_per_query: number;
  pass_rate: number | null;
  fallback_rate_pct: number;
}

// Query list
interface QueryRow {
  query_id: string;
  timestamp: string;
  query_text: string;
  agent_type: string;
  tools_used: string[];
  llm_calls: number;
  llm_models: string[];
  db_calls: number;
  external_calls: number;
  external_sources: string[];
  total_cost_usd: number;
  duration_ms: number;
  score: number | null;  // Only populated for assessment queries
  status: string;        // "completed" | "error" | "declined" | "timeout"
}

interface QueryListResponse {
  items: QueryRow[];
  total: number;
  page: number;
  size: number;
}

// Query detail
interface StepDetail {
  step_number: number;
  action: string;
  type_tag: "llm" | "db" | "external";
  model_name: string | null;
  input_summary: string | null;
  output_summary: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  cache_hit: boolean;
}

interface QueryDetailResponse {
  query_id: string;
  query_text: string;
  steps: StepDetail[];
  langfuse_trace_url: string | null;
}

// Grouped
interface GroupRow {
  key: string;
  query_count: number;
  total_cost_usd: number;
  avg_cost_usd: number;
  avg_latency_ms: number;
  error_rate: number;
}

interface GroupedResponse {
  group_by: string;
  bucket: string | null;
  groups: GroupRow[];
  total_queries: number;
}

// Assessment
interface AssessmentRunSummary {
  id: string;
  trigger: string;
  total_queries: number;
  passed_queries: number;
  pass_rate: number;
  total_cost_usd: number;
  started_at: string;
  completed_at: string;
}

interface AssessmentHistoryResponse {
  items: AssessmentRunSummary[];
}

interface LangfuseURLResponse {
  url: string | null;
}
```

## 6. New Utility Functions

### `formatMicroCurrency(value: number): string`
For sub-penny LLM costs. Returns "$0.0012" (4 decimal places). Falls back to `formatCurrency()` for values ≥$1.

### `formatDuration(ms: number): string`
For latency/duration display. Returns:
- `< 1000` → "350ms"
- `1000-59999` → "1.2s"
- `≥ 60000` → "2m 15s"

Both added to `frontend/src/lib/format.ts`.

## 7. Component Inventory

| Component | File | Description |
|---|---|---|
| `page.tsx` | `app/(authenticated)/observability/page.tsx` | Next.js route wrapper |
| `observability-client.tsx` | `app/(authenticated)/observability/observability-client.tsx` | Main page (use client) |
| `kpi-strip.tsx` | `app/(authenticated)/observability/_components/kpi-strip.tsx` | 5 StatTile KPI cards |
| `query-table.tsx` | `app/(authenticated)/observability/_components/query-table.tsx` | Sortable, filterable table |
| `query-row-detail.tsx` | `app/(authenticated)/observability/_components/query-row-detail.tsx` | Inline expansion timeline |
| `analytics-charts.tsx` | `app/(authenticated)/observability/_components/analytics-charts.tsx` | Grouped charts + dimension tabs |
| `assessment-section.tsx` | `app/(authenticated)/observability/_components/assessment-section.tsx` | Quality section |
| `use-observability.ts` | `hooks/use-observability.ts` | TanStack Query hooks (7 endpoints) |
| `use-current-user.ts` | `hooks/use-current-user.ts` | User profile + isAdmin hook |

## 8. Testing Requirements

~15-20 frontend tests:
- KPI strip: renders 5 tiles, handles null pass_rate, loading skeleton
- Query table: renders columns, sort click changes icon, status badge colors, empty state CTA
- Query row detail: expands on click, shows steps, Langfuse link renders when present
- Analytics charts: dimension tabs render, switching tab changes chart type
- Assessment section: renders pass rate, admin history conditionally rendered
- Navigation: Activity icon appears in sidebar
- Hooks: mock API responses, verify query keys and stale times
- Admin rendering: components hide when isAdmin=false, show when isAdmin=true

## 9. Resolved Design Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | `/auth/me` endpoint for role detection | Frontend has no role info — JWT doesn't embed role, no /me exists |
| 2 | `formatMicroCurrency()` for costs | Existing `formatCurrency()` is 2-decimal only |
| 3 | `formatDuration()` for latency | No ms→human-readable formatter exists |
| 4 | Inline expansion (not drawer/modal) | Steps are few (3-8), keeps table flow, no context switch |
| 5 | Tabs for chart dimensions (not dropdown) | Matches screener TAB_COLUMNS pattern |
| 6 | Score column admin-only | Score is null for 99% of non-admin queries |
| 7 | Assessment framed as platform quality | Non-admins have no personal assessment data |
| 8 | URL params for all state | Shareable, bookmarkable, matches screener pattern |
| 9 | Query list stale time 60s (not 30s) | Backend aggregation queries are expensive |
| 10 | Zone-based page structure | Matches dashboard pattern (each zone = separate component) |

## 10. Out of Scope

- Real-time WebSocket updates (polling with stale time is sufficient)
- CSV/Excel export of query data (future feature)
- Custom dashboard widgets / drag-and-drop layout
- Comparison views (this week vs last week)
- Alert configuration from the observability page
- Per-user score display (assessment scores are admin-only platform metrics)
