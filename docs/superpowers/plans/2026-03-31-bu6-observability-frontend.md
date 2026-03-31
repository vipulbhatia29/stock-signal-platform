# BU-6: Observability Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the observability page — KPI strip, query table with inline expansion, grouped analytics charts, assessment section — consuming the 7 backend API endpoints from BU-5.

**Architecture:** Zone-based page (matching dashboard pattern) with 4 zones: KPIs, charts, query table, assessment. Backend pre-req: `/auth/me` endpoint for role detection. New hooks in `use-observability.ts`, types in `api.ts`, format utils in `format.ts`. All admin-only UI conditionally rendered via `useCurrentUser()`.

**Tech Stack:** Next.js App Router, TanStack Query, Recharts, shadcn/ui, Tailwind CSS, existing navy design system tokens.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/routers/auth.py` | Modify | Add `GET /auth/me` endpoint |
| `backend/schemas/auth.py` | Modify | Add `UserProfileResponse` schema |
| `tests/api/test_auth_me.py` | Create | Tests for `/auth/me` |
| `frontend/src/types/api.ts` | Modify | Add observability + UserProfile types |
| `frontend/src/lib/format.ts` | Modify | Add `formatMicroCurrency`, `formatDuration` |
| `frontend/src/lib/auth.ts` | Modify | Extend context with user profile |
| `frontend/src/hooks/use-current-user.ts` | Create | `useCurrentUser()` hook |
| `frontend/src/hooks/use-observability.ts` | Create | 7 TanStack Query hooks |
| `frontend/src/components/sidebar-nav.tsx` | Modify | Add Observability nav item |
| `frontend/src/app/(authenticated)/observability/page.tsx` | Create | Route wrapper |
| `frontend/src/app/(authenticated)/observability/observability-client.tsx` | Create | Main page component |
| `frontend/src/app/(authenticated)/observability/_components/kpi-strip.tsx` | Create | 5 KPI StatTile cards |
| `frontend/src/app/(authenticated)/observability/_components/query-table.tsx` | Create | Sortable paginated table |
| `frontend/src/app/(authenticated)/observability/_components/query-row-detail.tsx` | Create | Inline expansion with steps |
| `frontend/src/app/(authenticated)/observability/_components/analytics-charts.tsx` | Create | Grouped dimension charts |
| `frontend/src/app/(authenticated)/observability/_components/assessment-section.tsx` | Create | Quality section |
| `frontend/src/__tests__/hooks/use-observability.test.ts` | Create | Hook tests |
| `frontend/src/__tests__/components/observability/*.test.tsx` | Create | Component tests |

---

## Chunk 1: Backend Pre-requisite — `/auth/me` Endpoint

### Task 1: Backend `/auth/me` endpoint + schema + tests

**Files:**
- Modify: `backend/schemas/auth.py`
- Modify: `backend/routers/auth.py`
- Create: `tests/api/test_auth_me.py`

- [ ] **Step 1: Add `UserProfileResponse` schema**

In `backend/schemas/auth.py`, add:

```python
class UserProfileResponse(BaseModel):
    """Current user profile returned by GET /auth/me."""
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
```

Import `uuid` at top of file if not present.

- [ ] **Step 2: Write failing tests for `/auth/me`**

Create `tests/api/test_auth_me.py`:

```python
"""Tests for GET /auth/me endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    """Unauthenticated request returns 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(authed_client: AsyncClient):
    """Authenticated request returns user profile with role."""
    resp = await authed_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "email" in data
    assert data["role"] in ("admin", "user")
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_me_returns_admin_role(admin_client: AsyncClient):
    """Admin user gets role=admin."""
    resp = await admin_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/api/test_auth_me.py -v
```

Expected: FAIL (404 — endpoint doesn't exist yet)

- [ ] **Step 4: Add `GET /auth/me` endpoint**

In `backend/routers/auth.py`, after the existing imports, add:

```python
from backend.schemas.auth import UserProfileResponse
```

Then add the endpoint (place it before the OIDC endpoints, around line 260):

```python
@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    user: User | CachedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """Return the current authenticated user's profile."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_active=user.is_active,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/api/test_auth_me.py -v
```

Expected: 3 PASSED (or 2 if `admin_client` fixture doesn't exist — check `conftest.py`)

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix backend/routers/auth.py backend/schemas/auth.py tests/api/test_auth_me.py && uv run ruff format backend/routers/auth.py backend/schemas/auth.py tests/api/test_auth_me.py
```

---

## Chunk 2: Frontend Foundation — Types, Formatters, User Hook

### Task 2: TypeScript types for observability

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Step 1: Add observability types to `api.ts`**

Append at the end of `frontend/src/types/api.ts`:

```typescript
// ── Observability ────────────────────────────────────────────────────────────

export interface UserProfile {
  id: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
}

export interface KPIResponse {
  queries_today: number;
  avg_latency_ms: number;
  avg_cost_per_query: number;
  pass_rate: number | null;
  fallback_rate_pct: number;
}

export interface QueryRow {
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
  score: number | null;
  status: string;
}

export interface QueryListResponse {
  items: QueryRow[];
  total: number;
  page: number;
  size: number;
}

export interface StepDetail {
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

export interface QueryDetailResponse {
  query_id: string;
  query_text: string;
  steps: StepDetail[];
  langfuse_trace_url: string | null;
}

export interface GroupRow {
  key: string;
  query_count: number;
  total_cost_usd: number;
  avg_cost_usd: number;
  avg_latency_ms: number;
  error_rate: number;
}

export interface GroupedResponse {
  group_by: string;
  bucket: string | null;
  groups: GroupRow[];
  total_queries: number;
}

export interface AssessmentRunSummary {
  id: string;
  trigger: string;
  total_queries: number;
  passed_queries: number;
  pass_rate: number;
  total_cost_usd: number;
  started_at: string;
  completed_at: string;
}

export interface AssessmentHistoryResponse {
  items: AssessmentRunSummary[];
}

export interface LangfuseURLResponse {
  url: string | null;
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors

---

### Task 3: Format utilities — `formatMicroCurrency` and `formatDuration`

**Files:**
- Modify: `frontend/src/lib/format.ts`
- Create: `frontend/src/__tests__/lib/format-observability.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/lib/format-observability.test.ts`:

```typescript
import { formatMicroCurrency, formatDuration } from "@/lib/format";

describe("formatMicroCurrency", () => {
  it("formats sub-penny values with 4 decimals", () => {
    expect(formatMicroCurrency(0.0012)).toBe("$0.0012");
  });

  it("formats zero", () => {
    expect(formatMicroCurrency(0)).toBe("$0.0000");
  });

  it("formats values >= $1 with 2 decimals", () => {
    expect(formatMicroCurrency(1.5)).toBe("$1.50");
  });

  it("handles null", () => {
    expect(formatMicroCurrency(null)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("formats milliseconds under 1s", () => {
    expect(formatDuration(350)).toBe("350ms");
  });

  it("formats seconds", () => {
    expect(formatDuration(1200)).toBe("1.2s");
  });

  it("formats minutes", () => {
    expect(formatDuration(135000)).toBe("2m 15s");
  });

  it("handles zero", () => {
    expect(formatDuration(0)).toBe("0ms");
  });

  it("handles null", () => {
    expect(formatDuration(null)).toBe("—");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx jest --testPathPattern="format-observability" --verbose
```

Expected: FAIL (functions not exported)

- [ ] **Step 3: Implement formatters**

Append to `frontend/src/lib/format.ts`:

```typescript
export function formatMicroCurrency(value: number | null): string {
  if (value === null) return "—";
  if (Math.abs(value) >= 1) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }
  return `$${value.toFixed(4)}`;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.round((ms % 60000) / 1000);
  return `${mins}m ${secs}s`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx jest --testPathPattern="format-observability" --verbose
```

Expected: 10 PASSED

- [ ] **Step 5: Commit**

---

### Task 4: `useCurrentUser` hook + auth context extension

**Files:**
- Create: `frontend/src/hooks/use-current-user.ts`
- Modify: `frontend/src/lib/auth.ts`
- Create: `frontend/src/__tests__/hooks/use-current-user.test.ts`

- [ ] **Step 1: Create `useCurrentUser` hook**

Create `frontend/src/hooks/use-current-user.ts`:

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type { UserProfile } from "@/types/api";

export function useCurrentUser(enabled = true) {
  const query = useQuery({
    queryKey: ["current-user"],
    queryFn: () => get<UserProfile>("/auth/me"),
    staleTime: Infinity,
    enabled,
  });

  return {
    ...query,
    user: query.data ?? null,
    isAdmin: query.data?.role === "admin",
  };
}
```

- [ ] **Step 2: Write tests**

Create `frontend/src/__tests__/hooks/use-current-user.test.ts`:

```typescript
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCurrentUser } from "@/hooks/use-current-user";
import * as api from "@/lib/api";
import React from "react";

jest.mock("@/lib/api", () => ({
  get: jest.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe("useCurrentUser", () => {
  it("returns user profile and isAdmin=false for regular user", async () => {
    (api.get as jest.Mock).mockResolvedValue({
      id: "u1",
      email: "test@example.com",
      role: "user",
      is_active: true,
    });
    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.user).not.toBeNull());
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.user?.email).toBe("test@example.com");
  });

  it("returns isAdmin=true for admin user", async () => {
    (api.get as jest.Mock).mockResolvedValue({
      id: "u2",
      email: "admin@example.com",
      role: "admin",
      is_active: true,
    });
    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.isAdmin).toBe(true));
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx jest --testPathPattern="use-current-user" --verbose
```

Expected: 2 PASSED

- [ ] **Step 4: Commit**

---

### Task 5: Observability TanStack Query hooks

**Files:**
- Create: `frontend/src/hooks/use-observability.ts`
- Create: `frontend/src/__tests__/hooks/use-observability.test.ts`

- [ ] **Step 1: Create hooks file**

Create `frontend/src/hooks/use-observability.ts`:

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { get } from "@/lib/api";
import type {
  KPIResponse,
  QueryListResponse,
  QueryDetailResponse,
  GroupedResponse,
  AssessmentRunSummary,
  AssessmentHistoryResponse,
} from "@/types/api";

// ── Query key factory ────────────────────────────────────────────────────────

export const obsKeys = {
  kpis: ["observability", "kpis"] as const,
  queries: (params: Record<string, string | number | undefined>) =>
    ["observability", "queries", params] as const,
  queryDetail: (queryId: string) =>
    ["observability", "query-detail", queryId] as const,
  grouped: (params: Record<string, string | undefined>) =>
    ["observability", "grouped", params] as const,
  assessmentLatest: ["observability", "assessment", "latest"] as const,
  assessmentHistory: ["observability", "assessment", "history"] as const,
};

// ── Hooks ────────────────────────────────────────────────────────────────────

export function useObservabilityKPIs() {
  return useQuery({
    queryKey: obsKeys.kpis,
    queryFn: () => get<KPIResponse>("/observability/kpis"),
    staleTime: 60_000,
  });
}

interface QueryListParams {
  page?: number;
  size?: number;
  sort_by?: string;
  sort_order?: string;
  status?: string;
  cost_min?: number;
  cost_max?: number;
  date_from?: string;
  date_to?: string;
}

export function useObservabilityQueries(params: QueryListParams = {}) {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.size) searchParams.set("size", String(params.size));
  if (params.sort_by) searchParams.set("sort_by", params.sort_by);
  if (params.sort_order) searchParams.set("sort_order", params.sort_order);
  if (params.status) searchParams.set("status", params.status);
  if (params.cost_min != null) searchParams.set("cost_min", String(params.cost_min));
  if (params.cost_max != null) searchParams.set("cost_max", String(params.cost_max));
  if (params.date_from) searchParams.set("date_from", params.date_from);
  if (params.date_to) searchParams.set("date_to", params.date_to);

  const qs = searchParams.toString();
  const path = `/observability/queries${qs ? `?${qs}` : ""}`;

  return useQuery({
    queryKey: obsKeys.queries(params as Record<string, string | number | undefined>),
    queryFn: () => get<QueryListResponse>(path),
    staleTime: 60_000,
  });
}

export function useQueryDetail(queryId: string | null) {
  return useQuery({
    queryKey: obsKeys.queryDetail(queryId ?? ""),
    queryFn: () => get<QueryDetailResponse>(`/observability/queries/${queryId}`),
    staleTime: Infinity,
    enabled: !!queryId,
  });
}

interface GroupedParams {
  group_by: string;
  bucket?: string;
  date_from?: string;
  date_to?: string;
}

export function useObservabilityGrouped(params: GroupedParams) {
  const searchParams = new URLSearchParams();
  searchParams.set("group_by", params.group_by);
  if (params.bucket) searchParams.set("bucket", params.bucket);
  if (params.date_from) searchParams.set("date_from", params.date_from);
  if (params.date_to) searchParams.set("date_to", params.date_to);

  return useQuery({
    queryKey: obsKeys.grouped(params as Record<string, string | undefined>),
    queryFn: () =>
      get<GroupedResponse>(`/observability/queries/grouped?${searchParams.toString()}`),
    staleTime: 120_000,
  });
}

export function useAssessmentLatest() {
  return useQuery({
    queryKey: obsKeys.assessmentLatest,
    queryFn: () => get<AssessmentRunSummary | null>("/observability/assessment/latest"),
    staleTime: 300_000,
  });
}

export function useAssessmentHistory(enabled = false) {
  return useQuery({
    queryKey: obsKeys.assessmentHistory,
    queryFn: () => get<AssessmentHistoryResponse>("/observability/assessment/history"),
    staleTime: 300_000,
    enabled,
  });
}
```

- [ ] **Step 2: Write hook tests**

Create `frontend/src/__tests__/hooks/use-observability.test.ts`:

```typescript
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useObservabilityKPIs,
  useObservabilityQueries,
  useQueryDetail,
  useObservabilityGrouped,
  useAssessmentLatest,
} from "@/hooks/use-observability";
import * as api from "@/lib/api";
import React from "react";

jest.mock("@/lib/api", () => ({
  get: jest.fn(),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

const mockGet = api.get as jest.Mock;

describe("useObservabilityKPIs", () => {
  it("fetches KPIs", async () => {
    mockGet.mockResolvedValue({
      queries_today: 42,
      avg_latency_ms: 1200,
      avg_cost_per_query: 0.003,
      pass_rate: 0.87,
      fallback_rate_pct: 0.02,
    });
    const { result } = renderHook(() => useObservabilityKPIs(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.queries_today).toBe(42);
    expect(mockGet).toHaveBeenCalledWith("/observability/kpis");
  });
});

describe("useObservabilityQueries", () => {
  it("passes query params", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, page: 1, size: 25 });
    const { result } = renderHook(
      () => useObservabilityQueries({ page: 2, status: "error" }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining("page=2")
    );
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining("status=error")
    );
  });
});

describe("useQueryDetail", () => {
  it("does not fetch when queryId is null", () => {
    renderHook(() => useQueryDetail(null), { wrapper });
    expect(mockGet).not.toHaveBeenCalledWith(
      expect.stringContaining("/observability/queries/")
    );
  });

  it("fetches when queryId is provided", async () => {
    mockGet.mockResolvedValue({
      query_id: "abc",
      query_text: "test",
      steps: [],
      langfuse_trace_url: null,
    });
    const { result } = renderHook(() => useQueryDetail("abc"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith("/observability/queries/abc");
  });
});

describe("useObservabilityGrouped", () => {
  it("sends group_by param", async () => {
    mockGet.mockResolvedValue({ group_by: "date", bucket: "day", groups: [], total_queries: 0 });
    const { result } = renderHook(
      () => useObservabilityGrouped({ group_by: "date", bucket: "day" }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining("group_by=date")
    );
  });
});

describe("useAssessmentLatest", () => {
  it("fetches latest assessment", async () => {
    mockGet.mockResolvedValue({ id: "r1", pass_rate: 0.85, total_queries: 20 });
    const { result } = renderHook(() => useAssessmentLatest(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockGet).toHaveBeenCalledWith("/observability/assessment/latest");
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx jest --testPathPattern="use-observability" --verbose
```

Expected: 5 PASSED

- [ ] **Step 4: Commit**

---

## Chunk 3: Navigation + Page Shell

### Task 6: Sidebar nav item + page route

**Files:**
- Modify: `frontend/src/components/sidebar-nav.tsx`
- Create: `frontend/src/app/(authenticated)/observability/page.tsx`
- Create: `frontend/src/app/(authenticated)/observability/observability-client.tsx`

- [ ] **Step 1: Add nav item**

In `frontend/src/components/sidebar-nav.tsx`, add `Activity` to the import:

```typescript
import {
  LayoutDashboard,
  Search,
  Briefcase,
  PieChart,
  Activity,
  Settings,
  LogOut,
} from "lucide-react";
```

Add to `NAV_ITEMS` array (after Sectors):

```typescript
const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener",  label: "Screener",  icon: Search },
  { href: "/portfolio", label: "Portfolio",  icon: Briefcase },
  { href: "/sectors",   label: "Sectors",    icon: PieChart },
  { href: "/observability", label: "Observability", icon: Activity },
] as const;
```

- [ ] **Step 2: Create page route**

Create `frontend/src/app/(authenticated)/observability/page.tsx`:

```tsx
import { ObservabilityClient } from "./observability-client";

export const metadata = { title: "Observability — Stock Signal Platform" };

export default function ObservabilityPage() {
  return <ObservabilityClient />;
}
```

- [ ] **Step 3: Create page shell**

Create `frontend/src/app/(authenticated)/observability/observability-client.tsx`:

```tsx
"use client";

import { Suspense } from "react";
import { PageTransition } from "@/components/motion-primitives";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/hooks/use-current-user";
import { KPIStrip } from "./_components/kpi-strip";
import { AnalyticsCharts } from "./_components/analytics-charts";
import { QueryTable } from "./_components/query-table";
import { AssessmentSection } from "./_components/assessment-section";

export function ObservabilityClient() {
  const { isAdmin } = useCurrentUser();

  return (
    <PageTransition className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Observability</h1>

      <KPIStrip />
      <AnalyticsCharts isAdmin={isAdmin} />
      <Suspense fallback={<Skeleton className="h-[400px] w-full rounded-lg bg-card2" />}>
        <QueryTable isAdmin={isAdmin} />
      </Suspense>
      <AssessmentSection isAdmin={isAdmin} />
    </PageTransition>
  );
}
```

- [ ] **Step 4: Create stub components**

Create `frontend/src/app/(authenticated)/observability/_components/kpi-strip.tsx`:

```tsx
"use client";

export function KPIStrip() {
  return <div data-testid="kpi-strip">KPI Strip placeholder</div>;
}
```

Create `frontend/src/app/(authenticated)/observability/_components/analytics-charts.tsx`:

```tsx
"use client";

export function AnalyticsCharts({ isAdmin }: { isAdmin: boolean }) {
  return <div data-testid="analytics-charts">Analytics Charts placeholder</div>;
}
```

Create `frontend/src/app/(authenticated)/observability/_components/query-table.tsx`:

```tsx
"use client";

export function QueryTable({ isAdmin }: { isAdmin: boolean }) {
  return <div data-testid="query-table">Query Table placeholder</div>;
}
```

Create `frontend/src/app/(authenticated)/observability/_components/assessment-section.tsx`:

```tsx
"use client";

export function AssessmentSection({ isAdmin }: { isAdmin: boolean }) {
  return <div data-testid="assessment-section">Assessment placeholder</div>;
}
```

- [ ] **Step 5: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: 0 errors

- [ ] **Step 6: Commit**

---

## Chunk 4: KPI Strip

### Task 7: KPI strip component

**Files:**
- Modify: `frontend/src/app/(authenticated)/observability/_components/kpi-strip.tsx`
- Create: `frontend/src/__tests__/components/observability/kpi-strip.test.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/__tests__/components/observability/kpi-strip.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KPIStrip } from "@/app/(authenticated)/observability/_components/kpi-strip";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(QueryClientProvider, { client: qc }, ui)
  );
}

describe("KPIStrip", () => {
  it("renders 5 KPI tiles when data is loaded", () => {
    (obsHooks.useObservabilityKPIs as jest.Mock).mockReturnValue({
      data: {
        queries_today: 42,
        avg_latency_ms: 1200,
        avg_cost_per_query: 0.003,
        pass_rate: 0.87,
        fallback_rate_pct: 0.02,
      },
      isLoading: false,
    });
    wrap(<KPIStrip />);
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(5);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders skeletons when loading", () => {
    (obsHooks.useObservabilityKPIs as jest.Mock).mockReturnValue({
      data: undefined,
      isLoading: true,
    });
    wrap(<KPIStrip />);
    const skeletons = document.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(5);
  });

  it("handles null pass_rate", () => {
    (obsHooks.useObservabilityKPIs as jest.Mock).mockReturnValue({
      data: {
        queries_today: 0,
        avg_latency_ms: 0,
        avg_cost_per_query: 0,
        pass_rate: null,
        fallback_rate_pct: 0,
      },
      isLoading: false,
    });
    wrap(<KPIStrip />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx jest --testPathPattern="kpi-strip" --verbose
```

Expected: FAIL

- [ ] **Step 3: Implement KPI strip**

Replace `frontend/src/app/(authenticated)/observability/_components/kpi-strip.tsx`:

```tsx
"use client";

import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { Skeleton } from "@/components/ui/skeleton";
import { StaggerGroup, StaggerItem } from "@/components/motion-primitives";
import { useObservabilityKPIs } from "@/hooks/use-observability";
import { formatMicroCurrency, formatDuration, formatPercent } from "@/lib/format";

function passRateAccent(rate: number | null): "gain" | "warn" | "loss" | "cyan" {
  if (rate === null) return "cyan";
  if (rate >= 0.8) return "gain";
  if (rate >= 0.5) return "warn";
  return "loss";
}

function fallbackAccent(rate: number): "gain" | "warn" | "loss" {
  if (rate < 0.05) return "gain";
  if (rate < 0.15) return "warn";
  return "loss";
}

export function KPIStrip() {
  const { data, isLoading } = useObservabilityKPIs();

  return (
    <section aria-label="Key Metrics">
      <SectionHeading>AI Agent Metrics</SectionHeading>

      {isLoading || !data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[72px] w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : (
        <StaggerGroup stagger={0.06} className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StaggerItem>
            <StatTile label="Queries Today" value={String(data.queries_today)} accentColor="cyan" />
          </StaggerItem>
          <StaggerItem>
            <StatTile label="Avg Latency" value={formatDuration(data.avg_latency_ms)} accentColor="cyan" />
          </StaggerItem>
          <StaggerItem>
            <StatTile label="Avg Cost / Query" value={formatMicroCurrency(data.avg_cost_per_query)} accentColor="cyan" />
          </StaggerItem>
          <StaggerItem>
            <StatTile
              label="Pass Rate"
              value={data.pass_rate !== null ? formatPercent(data.pass_rate) : "—"}
              accentColor={passRateAccent(data.pass_rate)}
            />
          </StaggerItem>
          <StaggerItem>
            <StatTile
              label="Error Rate"
              value={formatPercent(data.fallback_rate_pct)}
              accentColor={fallbackAccent(data.fallback_rate_pct)}
            />
          </StaggerItem>
        </StaggerGroup>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx jest --testPathPattern="kpi-strip" --verbose
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

---

## Chunk 5: Query Table + Inline Expansion

### Task 8: Query table component

**Files:**
- Modify: `frontend/src/app/(authenticated)/observability/_components/query-table.tsx`
- Create: `frontend/src/__tests__/components/observability/query-table.test.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/__tests__/components/observability/query-table.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueryTable } from "@/app/(authenticated)/observability/_components/query-table";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: jest.fn() }),
  usePathname: () => "/observability",
}));

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

const mockRow = {
  query_id: "q1",
  timestamp: "2026-03-31T10:00:00Z",
  query_text: "Analyze AAPL stock performance",
  agent_type: "react_v2",
  tools_used: ["get_stock_data", "analyze_stock", "get_fundamentals"],
  llm_calls: 3,
  llm_models: ["llama-3.3-70b"],
  db_calls: 2,
  external_calls: 1,
  external_sources: ["web_search"],
  total_cost_usd: 0.0045,
  duration_ms: 3200,
  score: null,
  status: "completed",
};

describe("QueryTable", () => {
  beforeEach(() => {
    (obsHooks.useObservabilityQueries as jest.Mock).mockReturnValue({
      data: { items: [mockRow], total: 1, page: 1, size: 25 },
      isLoading: false,
    });
    (obsHooks.useQueryDetail as jest.Mock).mockReturnValue({
      data: undefined,
      isLoading: false,
    });
  });

  it("renders table with query rows", () => {
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.getByText(/Analyze AAPL/)).toBeInTheDocument();
  });

  it("shows status badge with correct color", () => {
    wrap(<QueryTable isAdmin={false} />);
    const badge = screen.getByText("completed");
    expect(badge.className).toContain("text-gain");
  });

  it("caps tool badges at 3 with overflow", () => {
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.getByText("+1")).toBeInTheDocument();
  });

  it("shows empty state when no queries", () => {
    (obsHooks.useObservabilityQueries as jest.Mock).mockReturnValue({
      data: { items: [], total: 0, page: 1, size: 25 },
      isLoading: false,
    });
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.getByText(/No queries yet/)).toBeInTheDocument();
  });

  it("hides score column for non-admin", () => {
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
  });

  it("shows score column for admin", () => {
    wrap(<QueryTable isAdmin={true} />);
    expect(screen.getByText("Score")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement query table**

Replace `frontend/src/app/(authenticated)/observability/_components/query-table.tsx`:

```tsx
"use client";

import { Fragment, useState, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { ChevronUp, ChevronDown, MessageSquare } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { useObservabilityQueries, useQueryDetail } from "@/hooks/use-observability";
import { formatMicroCurrency, formatDuration, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { QueryRowDetail } from "./query-row-detail";

const MAX_TOOL_BADGES = 3;

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-gdim text-gain",
  error: "bg-ldim text-loss",
  declined: "bg-wdim text-warning",
  timeout: "bg-muted text-muted-foreground",
};

interface Column {
  key: string;
  label: string;
  sortable: boolean;
  adminOnly?: boolean;
}

const COLUMNS: Column[] = [
  { key: "timestamp", label: "Time", sortable: true },
  { key: "query_text", label: "Query", sortable: false },
  { key: "agent_type", label: "Agent", sortable: false },
  { key: "tools_used", label: "Tools", sortable: false },
  { key: "llm_calls", label: "LLM Calls", sortable: true },
  { key: "total_cost_usd", label: "Cost", sortable: true },
  { key: "duration_ms", label: "Duration", sortable: true },
  { key: "status", label: "Status", sortable: false },
  { key: "score", label: "Score", sortable: true, adminOnly: true },
];

export function QueryTable({ isAdmin }: { isAdmin: boolean }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const page = Number(searchParams.get("page") ?? "1");
  const sortBy = searchParams.get("sort") ?? "timestamp";
  const sortOrder = (searchParams.get("order") ?? "desc") as "asc" | "desc";
  const statusFilter = searchParams.get("status") ?? undefined;

  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useObservabilityQueries({
    page,
    sort_by: sortBy,
    sort_order: sortOrder,
    status: statusFilter,
  });

  const { data: detail, isLoading: detailLoading } = useQueryDetail(expandedId);

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([k, v]) => {
        if (v === undefined) params.delete(k);
        else params.set(k, v);
      });
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [searchParams, router, pathname],
  );

  const handleSort = (col: string) => {
    if (col === sortBy) {
      updateParams({ order: sortOrder === "desc" ? "asc" : "desc" });
    } else {
      updateParams({ sort: col, order: "desc" });
    }
  };

  const handleRowClick = (queryId: string) => {
    setExpandedId((prev) => (prev === queryId ? null : queryId));
  };

  const visibleCols = COLUMNS.filter((c) => !c.adminOnly || isAdmin);
  const totalPages = data ? Math.ceil(data.total / (data.size || 25)) : 0;

  return (
    <section aria-label="Query History">
      <SectionHeading>Query History</SectionHeading>

      {/* Status filter pills */}
      <div className="mb-3 flex gap-2">
        {["all", "completed", "error", "declined", "timeout"].map((s) => (
          <button
            key={s}
            onClick={() => updateParams({ status: s === "all" ? undefined : s, page: "1" })}
            className={cn(
              "rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors",
              (s === "all" && !statusFilter) || statusFilter === s
                ? "bg-cyan/15 text-cyan"
                : "bg-card2 text-muted-foreground hover:text-foreground",
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <MessageSquare className="h-10 w-10 text-subtle" />
          <p className="text-sm text-muted-foreground">No queries yet — try asking the AI agent a question!</p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-card2">
                  {visibleCols.map((col) => (
                    <th
                      key={col.key}
                      className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle"
                      aria-sort={col.sortable && col.key === sortBy ? sortOrder === "asc" ? "ascending" : "descending" : undefined}
                    >
                      {col.sortable ? (
                        <button
                          className="inline-flex items-center gap-1 hover:text-foreground"
                          onClick={() => handleSort(col.key)}
                        >
                          {col.label}
                          {col.key === sortBy && (
                            sortOrder === "asc"
                              ? <ChevronUp className="h-3 w-3" />
                              : <ChevronDown className="h-3 w-3" />
                          )}
                        </button>
                      ) : (
                        col.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <Fragment key={row.query_id}>
                    <tr
                      role="button"
                      tabIndex={0}
                      aria-expanded={expandedId === row.query_id}
                      onClick={() => handleRowClick(row.query_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleRowClick(row.query_id);
                        }
                      }}
                      className="cursor-pointer border-t border-border/40 transition-colors hover:bg-hov"
                    >
                      <td className="px-3 py-2 text-muted-foreground text-xs whitespace-nowrap">
                        {formatRelativeTime(row.timestamp)}
                      </td>
                      <td className="px-3 py-2 max-w-[200px] truncate text-foreground">
                        {row.query_text}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {row.agent_type}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {row.tools_used.slice(0, MAX_TOOL_BADGES).map((t) => (
                            <span key={t} className="rounded-full bg-cdim px-2 py-0.5 text-[10px] font-medium text-cyan">
                              {t}
                            </span>
                          ))}
                          {row.tools_used.length > MAX_TOOL_BADGES && (
                            <span className="rounded-full bg-card2 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                              +{row.tools_used.length - MAX_TOOL_BADGES}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                        {row.llm_calls}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-foreground">
                        {formatMicroCurrency(row.total_cost_usd)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                        {formatDuration(row.duration_ms)}
                      </td>
                      <td className="px-3 py-2">
                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", STATUS_STYLES[row.status] ?? "bg-muted text-muted-foreground")}>
                          {row.status}
                        </span>
                      </td>
                      {isAdmin && (
                        <td className="px-3 py-2 font-mono text-xs">
                          {row.score !== null ? (
                            <span className={cn(row.score >= 8 ? "text-gain" : row.score >= 5 ? "text-warning" : "text-loss")}>
                              {row.score.toFixed(1)}
                            </span>
                          ) : (
                            <span className="text-subtle">—</span>
                          )}
                        </td>
                      )}
                    </tr>
                    {expandedId === row.query_id && (
                      <tr>
                        <td colSpan={visibleCols.length} className="bg-card2/50 px-4 py-3">
                          <QueryRowDetail
                            detail={detail ?? null}
                            isLoading={detailLoading}
                            queryText={row.query_text}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Page {data.page} of {totalPages} ({data.total} queries)
              </span>
              <div className="flex gap-2">
                <button
                  disabled={data.page <= 1}
                  onClick={() => updateParams({ page: String(data.page - 1) })}
                  className="rounded-lg bg-card2 px-3 py-1.5 transition-colors hover:bg-hov disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  disabled={data.page >= totalPages}
                  onClick={() => updateParams({ page: String(data.page + 1) })}
                  className="rounded-lg bg-card2 px-3 py-1.5 transition-colors hover:bg-hov disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx jest --testPathPattern="query-table" --verbose
```

Expected: 6 PASSED

- [ ] **Step 4: Commit**

---

### Task 9: Query row detail (inline expansion)

**Files:**
- Modify: `frontend/src/app/(authenticated)/observability/_components/query-row-detail.tsx`
- Create: `frontend/src/__tests__/components/observability/query-row-detail.test.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/__tests__/components/observability/query-row-detail.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryRowDetail } from "@/app/(authenticated)/observability/_components/query-row-detail";

const mockDetail = {
  query_id: "q1",
  query_text: "Analyze AAPL fundamentals and forecast",
  steps: [
    { step_number: 1, action: "llm.groq.llama-3.3-70b", type_tag: "llm" as const, model_name: "llama-3.3-70b", input_summary: "→ groq/llama-3.3-70b", output_summary: "256 tokens, 1200ms, $0.0012", latency_ms: 1200, cost_usd: 0.0012, cache_hit: false },
    { step_number: 2, action: "tool.get_stock_data", type_tag: "db" as const, model_name: null, input_summary: '{"ticker": "AAPL"}', output_summary: "1 row, 45 fields", latency_ms: 50, cost_usd: null, cache_hit: true },
    { step_number: 3, action: "tool.web_search", type_tag: "external" as const, model_name: null, input_summary: '{"query": "AAPL news"}', output_summary: "3 results", latency_ms: 800, cost_usd: null, cache_hit: false },
  ],
  langfuse_trace_url: "https://langfuse.example.com/trace/abc",
};

describe("QueryRowDetail", () => {
  it("renders all steps", () => {
    render(<QueryRowDetail detail={mockDetail} isLoading={false} queryText="Analyze AAPL" />);
    expect(screen.getByText("llm.groq.llama-3.3-70b")).toBeInTheDocument();
    expect(screen.getByText("tool.get_stock_data")).toBeInTheDocument();
    expect(screen.getByText("tool.web_search")).toBeInTheDocument();
  });

  it("shows type tag pills with correct labels", () => {
    render(<QueryRowDetail detail={mockDetail} isLoading={false} queryText="Analyze AAPL" />);
    expect(screen.getByText("llm")).toBeInTheDocument();
    expect(screen.getByText("db")).toBeInTheDocument();
    expect(screen.getByText("external")).toBeInTheDocument();
  });

  it("shows cached badge", () => {
    render(<QueryRowDetail detail={mockDetail} isLoading={false} queryText="Analyze AAPL" />);
    expect(screen.getByText("cached")).toBeInTheDocument();
  });

  it("shows Langfuse link when URL present", () => {
    render(<QueryRowDetail detail={mockDetail} isLoading={false} queryText="Analyze AAPL" />);
    const link = screen.getByText("View in Langfuse");
    expect(link).toHaveAttribute("href", mockDetail.langfuse_trace_url);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("hides Langfuse link when URL is null", () => {
    const noTrace = { ...mockDetail, langfuse_trace_url: null };
    render(<QueryRowDetail detail={noTrace} isLoading={false} queryText="test" />);
    expect(screen.queryByText("View in Langfuse")).not.toBeInTheDocument();
  });

  it("shows loading skeleton", () => {
    render(<QueryRowDetail detail={null} isLoading={true} queryText="test" />);
    const skeletons = document.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Implement detail component**

Replace `frontend/src/app/(authenticated)/observability/_components/query-row-detail.tsx`:

```tsx
"use client";

import { ExternalLink } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMicroCurrency, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { QueryDetailResponse } from "@/types/api";

const TYPE_TAG_STYLES: Record<string, string> = {
  llm: "bg-purple-500/15 text-purple-400",
  db: "bg-cdim text-cyan",
  external: "bg-wdim text-warning",
};

interface Props {
  detail: QueryDetailResponse | null;
  isLoading: boolean;
  queryText: string;
}

export function QueryRowDetail({ detail, isLoading, queryText }: Props) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg bg-card2" />
        ))}
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="space-y-3">
      {/* Full query text */}
      <p className="text-sm text-foreground">{detail.query_text || queryText}</p>

      {/* Steps timeline */}
      <div className="space-y-2">
        {detail.steps.map((step) => (
          <div
            key={step.step_number}
            className="flex items-start gap-3 rounded-lg border border-border/30 bg-card p-3"
          >
            {/* Step number */}
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-card2 text-[10px] font-bold text-muted-foreground">
              {step.step_number}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {/* Action name */}
                <span className="font-mono text-xs font-medium text-foreground">
                  {step.action}
                </span>

                {/* Type tag */}
                <span className={cn("rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase", TYPE_TAG_STYLES[step.type_tag] ?? "bg-muted text-muted-foreground")}>
                  {step.type_tag}
                </span>

                {/* Cache hit */}
                {step.cache_hit && (
                  <span className="rounded-full bg-gdim px-2 py-0.5 text-[9px] font-semibold text-gain">
                    cached
                  </span>
                )}
              </div>

              {/* Summaries */}
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
                {step.input_summary && <span>In: {step.input_summary}</span>}
                {step.output_summary && <span>Out: {step.output_summary}</span>}
                {step.latency_ms != null && <span>{formatDuration(step.latency_ms)}</span>}
                {step.cost_usd != null && <span>{formatMicroCurrency(step.cost_usd)}</span>}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Langfuse link */}
      {detail.langfuse_trace_url && (
        <a
          href={detail.langfuse_trace_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-card2 px-3 py-1.5 text-xs font-medium text-cyan transition-colors hover:bg-hov"
        >
          <ExternalLink className="h-3 w-3" />
          View in Langfuse
        </a>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx jest --testPathPattern="query-row-detail" --verbose
```

Expected: 6 PASSED

- [ ] **Step 4: Commit**

---

## Chunk 6: Analytics Charts

### Task 10: Grouped analytics charts with dimension tabs

**Files:**
- Modify: `frontend/src/app/(authenticated)/observability/_components/analytics-charts.tsx`
- Create: `frontend/src/__tests__/components/observability/analytics-charts.test.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/__tests__/components/observability/analytics-charts.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnalyticsCharts } from "@/app/(authenticated)/observability/_components/analytics-charts";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="chart-container">{children}</div>,
  ComposedChart: ({ children }: { children: React.ReactNode }) => <div data-testid="composed-chart">{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
  Line: () => <div />,
  Bar: () => <div />,
  Area: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
}));

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

describe("AnalyticsCharts", () => {
  beforeEach(() => {
    (obsHooks.useObservabilityGrouped as jest.Mock).mockReturnValue({
      data: {
        group_by: "date",
        bucket: "day",
        groups: [
          { key: "2026-03-30", query_count: 10, total_cost_usd: 0.05, avg_cost_usd: 0.005, avg_latency_ms: 1200, error_rate: 0.1 },
          { key: "2026-03-31", query_count: 15, total_cost_usd: 0.08, avg_cost_usd: 0.005, avg_latency_ms: 1100, error_rate: 0.05 },
        ],
        total_queries: 25,
      },
      isLoading: false,
    });
  });

  it("renders dimension tabs", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.getByText("Over Time")).toBeInTheDocument();
    expect(screen.getByText("By Model")).toBeInTheDocument();
    expect(screen.getByText("By Provider")).toBeInTheDocument();
  });

  it("hides admin-only tabs for non-admin", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.queryByText("By User")).not.toBeInTheDocument();
  });

  it("shows admin-only tabs for admin", () => {
    wrap(<AnalyticsCharts isAdmin={true} />);
    expect(screen.getByText("By User")).toBeInTheDocument();
    expect(screen.getByText("By Intent")).toBeInTheDocument();
  });

  it("switches dimension on tab click", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    fireEvent.click(screen.getByText("By Model"));
    expect(obsHooks.useObservabilityGrouped).toHaveBeenCalledWith(
      expect.objectContaining({ group_by: "model" })
    );
  });

  it("renders chart container", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.getByTestId("chart-container")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement analytics charts**

Replace `frontend/src/app/(authenticated)/observability/_components/analytics-charts.tsx`:

```tsx
"use client";

import { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  BarChart,
  Line,
  Bar,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { useObservabilityGrouped } from "@/hooks/use-observability";
import { formatChartDate, formatMicroCurrency, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

interface DimensionTab {
  key: string;
  label: string;
  adminOnly?: boolean;
}

const DIMENSIONS: DimensionTab[] = [
  { key: "date", label: "Over Time" },
  { key: "model", label: "By Model" },
  { key: "provider", label: "By Provider" },
  { key: "agent_type", label: "By Agent" },
  { key: "status", label: "By Status" },
  { key: "tool_name", label: "By Tool" },
  { key: "user", label: "By User", adminOnly: true },
  { key: "intent_category", label: "By Intent", adminOnly: true },
];

const BUCKETS = ["day", "week", "month"] as const;

export function AnalyticsCharts({ isAdmin }: { isAdmin: boolean }) {
  const [dimension, setDimension] = useState("date");
  const [bucket, setBucket] = useState<(typeof BUCKETS)[number]>("day");
  const colors = useChartColors();

  const { data, isLoading } = useObservabilityGrouped({
    group_by: dimension,
    bucket: dimension === "date" ? bucket : undefined,
  });

  const visibleDims = DIMENSIONS.filter((d) => !d.adminOnly || isAdmin);
  const isDateDim = dimension === "date";

  const chartData = (data?.groups ?? []).map((g) => ({
    ...g,
    label: isDateDim ? formatChartDate(g.key) : g.key,
  }));

  return (
    <section aria-label="Analytics">
      <SectionHeading>Usage Analytics</SectionHeading>

      {/* Dimension tabs */}
      <div className="mb-3 flex flex-wrap gap-2">
        {visibleDims.map((d) => (
          <button
            key={d.key}
            onClick={() => setDimension(d.key)}
            className={cn(
              "rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors",
              dimension === d.key
                ? "bg-cyan/15 text-cyan"
                : "bg-card2 text-muted-foreground hover:text-foreground",
            )}
          >
            {d.label}
          </button>
        ))}
      </div>

      {/* Bucket selector for date dimension */}
      {isDateDim && (
        <div className="mb-3 flex gap-1.5">
          {BUCKETS.map((b) => (
            <button
              key={b}
              onClick={() => setBucket(b)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[10px] font-medium capitalize transition-colors",
                bucket === b ? "bg-card2 text-foreground" : "text-subtle hover:text-muted-foreground",
              )}
            >
              {b}
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <Skeleton className="h-[260px] w-full rounded-lg bg-card2" />
      ) : !chartData.length ? (
        <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
          Not enough data to show trends
        </div>
      ) : isDateDim ? (
        /* Line chart for date dimension */
        <div className="rounded-lg border border-border bg-card p-4">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData}>
              <CartesianGrid {...CHART_STYLE.grid} />
              <XAxis dataKey="label" {...CHART_STYLE.axis} />
              <YAxis
                yAxisId="cost"
                orientation="left"
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                {...CHART_STYLE.axis}
              />
              <YAxis
                yAxisId="latency"
                orientation="right"
                tickFormatter={(v: number) => `${Math.round(v)}ms`}
                {...CHART_STYLE.axis}
              />
              <Tooltip
                contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
                labelStyle={{ color: "var(--foreground)" }}
              />
              <Area
                yAxisId="cost"
                dataKey="total_cost_usd"
                stroke={colors.price}
                fill={colors.price}
                fillOpacity={0.1}
                name="Cost"
              />
              <Line
                yAxisId="latency"
                dataKey="avg_latency_ms"
                stroke={colors.sma200}
                dot={false}
                name="Avg Latency"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        /* Bar chart for categorical dimensions */
        <div className="rounded-lg border border-border bg-card p-4">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} layout={dimension === "tool_name" ? "vertical" : "horizontal"}>
              <CartesianGrid {...CHART_STYLE.grid} />
              {dimension === "tool_name" ? (
                <>
                  <YAxis dataKey="label" type="category" width={120} {...CHART_STYLE.axis} />
                  <XAxis type="number" {...CHART_STYLE.axis} />
                </>
              ) : (
                <>
                  <XAxis dataKey="label" {...CHART_STYLE.axis} />
                  <YAxis {...CHART_STYLE.axis} />
                </>
              )}
              <Tooltip
                contentStyle={{ backgroundColor: "var(--card)", border: "1px solid var(--border)", borderRadius: "var(--radius)" }}
                labelStyle={{ color: "var(--foreground)" }}
              />
              <Bar dataKey="query_count" fill={colors.price} name="Queries" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx jest --testPathPattern="analytics-charts" --verbose
```

Expected: 5 PASSED

- [ ] **Step 4: Commit**

---

## Chunk 7: Assessment Section + Final Verification

### Task 11: Assessment quality section

**Files:**
- Modify: `frontend/src/app/(authenticated)/observability/_components/assessment-section.tsx`
- Create: `frontend/src/__tests__/components/observability/assessment-section.test.tsx`

- [ ] **Step 1: Write tests**

Create `frontend/src/__tests__/components/observability/assessment-section.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AssessmentSection } from "@/app/(authenticated)/observability/_components/assessment-section";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

describe("AssessmentSection", () => {
  it("renders pass rate from latest assessment", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({
      data: {
        id: "r1",
        trigger: "weekly_ci",
        total_queries: 20,
        passed_queries: 17,
        pass_rate: 0.85,
        total_cost_usd: 0.12,
        started_at: "2026-03-30T00:00:00Z",
        completed_at: "2026-03-30T00:05:00Z",
      },
      isLoading: false,
    });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({ data: undefined, isLoading: false });
    wrap(<AssessmentSection isAdmin={false} />);
    expect(screen.getByText("85.0%")).toBeInTheDocument();
    expect(screen.getByText(/20 queries tested/)).toBeInTheDocument();
  });

  it("shows coming soon when no data", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({ data: null, isLoading: false });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({ data: undefined, isLoading: false });
    wrap(<AssessmentSection isAdmin={false} />);
    expect(screen.getByText(/Quality benchmarks coming soon/)).toBeInTheDocument();
  });

  it("hides history table for non-admin", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({
      data: { id: "r1", pass_rate: 0.85, total_queries: 20, passed_queries: 17, total_cost_usd: 0.12, trigger: "weekly_ci", started_at: "2026-03-30T00:00:00Z", completed_at: "2026-03-30T00:05:00Z" },
      isLoading: false,
    });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({ data: undefined, isLoading: false });
    wrap(<AssessmentSection isAdmin={false} />);
    expect(screen.queryByText("Assessment History")).not.toBeInTheDocument();
  });

  it("shows history table for admin", () => {
    (obsHooks.useAssessmentLatest as jest.Mock).mockReturnValue({
      data: { id: "r1", pass_rate: 0.85, total_queries: 20, passed_queries: 17, total_cost_usd: 0.12, trigger: "weekly_ci", started_at: "2026-03-30T00:00:00Z", completed_at: "2026-03-30T00:05:00Z" },
      isLoading: false,
    });
    (obsHooks.useAssessmentHistory as jest.Mock).mockReturnValue({
      data: { items: [{ id: "r1", trigger: "weekly_ci", pass_rate: 0.85, total_queries: 20, passed_queries: 17, total_cost_usd: 0.12, started_at: "2026-03-30T00:00:00Z", completed_at: "2026-03-30T00:05:00Z" }] },
      isLoading: false,
    });
    wrap(<AssessmentSection isAdmin={true} />);
    expect(screen.getByText("Assessment History")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement assessment section**

Replace `frontend/src/app/(authenticated)/observability/_components/assessment-section.tsx`:

```tsx
"use client";

import { Shield } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { Skeleton } from "@/components/ui/skeleton";
import { useAssessmentLatest, useAssessmentHistory } from "@/hooks/use-observability";
import { formatPercent, formatMicroCurrency, formatRelativeTime, formatDate } from "@/lib/format";

function passRateAccent(rate: number): "gain" | "warn" | "loss" {
  if (rate >= 0.8) return "gain";
  if (rate >= 0.5) return "warn";
  return "loss";
}

export function AssessmentSection({ isAdmin }: { isAdmin: boolean }) {
  const { data: latest, isLoading } = useAssessmentLatest();
  const { data: history } = useAssessmentHistory(isAdmin);

  return (
    <section aria-label="AI Quality">
      <SectionHeading>AI Quality</SectionHeading>

      {isLoading ? (
        <Skeleton className="h-[72px] w-full rounded-lg bg-card2" />
      ) : !latest ? (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <Shield className="h-8 w-8 text-subtle" />
          <p className="text-sm text-muted-foreground">
            Quality benchmarks coming soon — we regularly test AI accuracy against curated datasets.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              label="Pass Rate"
              value={formatPercent(latest.pass_rate)}
              accentColor={passRateAccent(latest.pass_rate)}
            />
            <StatTile
              label="Queries Tested"
              value={String(latest.total_queries)}
              sub={<span className="text-[10px] text-muted-foreground">{latest.passed_queries} passed</span>}
              accentColor="cyan"
            />
            <StatTile
              label="Test Cost"
              value={formatMicroCurrency(latest.total_cost_usd)}
              accentColor="cyan"
            />
            <StatTile
              label="Last Tested"
              value={formatRelativeTime(latest.completed_at)}
              sub={<span className="text-[10px] text-muted-foreground">{latest.trigger}</span>}
              accentColor="cyan"
            />
          </div>

          <p className="text-[11px] text-subtle">
            We regularly test AI quality against {latest.total_queries} benchmark queries to ensure accurate recommendations.
          </p>

          {/* Admin-only: assessment history */}
          {isAdmin && history?.items && history.items.length > 0 && (
            <div>
              <h3 className="mb-2 text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">
                Assessment History
              </h3>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-card2">
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Date</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Trigger</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Pass Rate</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Queries</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.items.map((run) => (
                      <tr key={run.id} className="border-t border-border/40">
                        <td className="px-3 py-2 text-xs text-muted-foreground">{formatDate(run.completed_at)}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">{run.trigger}</td>
                        <td className="px-3 py-2 font-mono text-xs text-foreground">{formatPercent(run.pass_rate)}</td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{run.total_queries}</td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{formatMicroCurrency(run.total_cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Run tests**

```bash
cd frontend && npx jest --testPathPattern="assessment-section" --verbose
```

Expected: 4 PASSED

- [ ] **Step 4: Commit**

---

### Task 12: Full verification — lint, type-check, all tests

**Files:** All files from Tasks 1-11

- [ ] **Step 1: Backend tests**

```bash
uv run pytest tests/api/test_auth_me.py -v
```

Expected: All PASSED

- [ ] **Step 2: Backend lint**

```bash
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
```

Expected: 0 errors

- [ ] **Step 3: Frontend type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Frontend lint**

```bash
cd frontend && npm run lint
```

Expected: 0 errors

- [ ] **Step 5: Frontend tests**

```bash
cd frontend && npx jest --verbose
```

Expected: All existing + new tests PASS (~20 new tests)

- [ ] **Step 6: Build check**

```bash
cd frontend && npm run build
```

Expected: Build succeeds (catches SSR issues)

- [ ] **Step 7: Final commit**

```bash
git add -A && git commit -m "feat(KAN-232): BU-6 observability frontend — complete"
```
