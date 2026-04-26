# Spec C: Admin Enhancements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 admin features to the Command Center and Pipeline Control pages: Forecast Health panel, System Health drill-down, and Audit Log viewer.

**Architecture:** All frontend-only — no backend changes. Uses existing `useCommandCenter()` aggregate data for CC features, adds a new `useAuditLog()` hook for the audit log endpoint. Follows established CC panel patterns.

**Tech Stack:** Next.js 15, TypeScript, TanStack Query, shadcn/ui Sheet, Recharts (none needed here), Tailwind v4

**Spec:** `docs/superpowers/specs/2026-04-26-ui-overhaul-spec-c-admin-enhancements.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `frontend/src/types/command-center.ts` | Add `ForecastHealthZone` interface + extend `CommandCenterResponse` |
| Create | `frontend/src/components/command-center/forecast-health-panel.tsx` | Forecast health panel with 2 metric cards |
| Modify | `frontend/src/app/(authenticated)/admin/command-center/page.tsx` | Wire 5th panel into grid |
| Modify | `frontend/src/components/command-center/system-health-panel.tsx` | Add "View Details" button + DrillDownSheet |
| Modify | `frontend/src/types/api.ts` | Add `AuditLogEntry` + `AuditLogResponse` types |
| Modify | `frontend/src/hooks/use-admin-pipelines.ts` | Add `useAuditLog()` hook + query key |
| Create | `frontend/src/components/admin/audit-log-table.tsx` | Audit log table with pagination + filter |
| Modify | `frontend/src/app/(authenticated)/admin/pipelines/page.tsx` | Wire audit log section |
| Create | `frontend/src/__tests__/admin/forecast-health-panel.test.tsx` | Tests for forecast health panel |
| Create | `frontend/src/__tests__/admin/system-health-drilldown.test.tsx` | Tests for system health drill-down |
| Create | `frontend/src/__tests__/admin/audit-log-table.test.tsx` | Tests for audit log table |

---

## Hard Constraints

1. **No backend changes** — all endpoints already exist and return the needed data.
2. **Follow established CC panel patterns** — same card styling, same grid layout, same DrillDownSheet component.
3. **No `any` types** — TypeScript strict mode.
4. **All data fetching through TanStack Query hooks** — never raw fetch in components.
5. **API paths use `/admin/pipelines/...` NOT `/api/v1/admin/pipelines/...`** — `api.ts` prepends the base.

---

### Task 1: Add ForecastHealthZone type and extend CommandCenterResponse

**Files:**
- Modify: `frontend/src/types/command-center.ts:121-128`

- [ ] **Step 1: Add ForecastHealthZone interface**

Add before `CommandCenterResponse` in `frontend/src/types/command-center.ts`:

```typescript
export interface ForecastHealthZone {
  backtest_health_pct: number;
  models_passing: number;
  models_total: number;
  sentiment_coverage_pct: number;
  tickers_with_sentiment: number;
  tickers_total: number;
}
```

- [ ] **Step 2: Extend CommandCenterResponse**

Add `forecast_health` field to `CommandCenterResponse`:

```typescript
export interface CommandCenterResponse {
  timestamp: string;
  meta: CommandCenterMeta;
  system_health: SystemHealthZone | null;
  api_traffic: ApiTrafficZone | null;
  llm_operations: LlmOperationsZone | null;
  pipeline: PipelineZone | null;
  forecast_health: ForecastHealthZone | null;
}
```

- [ ] **Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (additive type change, no consumers yet)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/command-center.ts
git commit -m "feat(types): add ForecastHealthZone to CommandCenterResponse"
```

---

### Task 2: Create ForecastHealthPanel component

**Files:**
- Create: `frontend/src/components/command-center/forecast-health-panel.tsx`
- Create: `frontend/src/__tests__/admin/forecast-health-panel.test.tsx`

- [ ] **Step 1: Write the tests**

Create `frontend/src/__tests__/admin/forecast-health-panel.test.tsx`:

```typescript
import React from "react";
import { render, screen } from "@testing-library/react";
import { ForecastHealthPanel } from "@/components/command-center/forecast-health-panel";
import type { ForecastHealthZone } from "@/types/command-center";

const MOCK_HEALTHY: ForecastHealthZone = {
  backtest_health_pct: 85.0,
  models_passing: 17,
  models_total: 20,
  sentiment_coverage_pct: 92.0,
  tickers_with_sentiment: 46,
  tickers_total: 50,
};

const MOCK_DEGRADED: ForecastHealthZone = {
  backtest_health_pct: 55.0,
  models_passing: 5,
  models_total: 9,
  sentiment_coverage_pct: 40.0,
  tickers_with_sentiment: 8,
  tickers_total: 20,
};

const MOCK_AMBER: ForecastHealthZone = {
  backtest_health_pct: 70.0,
  models_passing: 7,
  models_total: 10,
  sentiment_coverage_pct: 65.0,
  tickers_with_sentiment: 13,
  tickers_total: 20,
};

test("renders backtest and sentiment metrics with correct values", () => {
  render(<ForecastHealthPanel data={MOCK_HEALTHY} />);
  expect(screen.getByText("Forecast Health")).toBeInTheDocument();
  expect(screen.getByText("85%")).toBeInTheDocument();
  expect(screen.getByText("17/20 models")).toBeInTheDocument();
  expect(screen.getByText("92%")).toBeInTheDocument();
  expect(screen.getByText("46/50 tickers")).toBeInTheDocument();
});

test("renders green color for metrics >= 80%", () => {
  const { container } = render(<ForecastHealthPanel data={MOCK_HEALTHY} />);
  const greenElements = container.querySelectorAll(".text-emerald-400");
  expect(greenElements.length).toBeGreaterThanOrEqual(2);
});

test("renders red color for metrics < 60%", () => {
  const { container } = render(<ForecastHealthPanel data={MOCK_DEGRADED} />);
  const redElements = container.querySelectorAll(".text-red-400");
  expect(redElements.length).toBeGreaterThanOrEqual(2);
});

test("renders amber color for metrics 60-79%", () => {
  const { container } = render(<ForecastHealthPanel data={MOCK_AMBER} />);
  const amberElements = container.querySelectorAll(".text-yellow-400");
  expect(amberElements.length).toBeGreaterThanOrEqual(2);
});

test("renders unavailable state when data is null", () => {
  render(<ForecastHealthPanel data={null} />);
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx jest --testPathPattern=forecast-health-panel --no-coverage`
Expected: FAIL — module not found

- [ ] **Step 3: Create the component**

Create `frontend/src/components/command-center/forecast-health-panel.tsx`:

```typescript
"use client";

import type { ForecastHealthZone } from "@/types/command-center";

interface ForecastHealthPanelProps {
  data: ForecastHealthZone | null;
}

function healthColor(pct: number): string {
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 60) return "text-yellow-400";
  return "text-red-400";
}

export function ForecastHealthPanel({ data }: ForecastHealthPanelProps) {
  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">Forecast Health</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  const backtestPct = Math.round(data.backtest_health_pct);
  const sentimentPct = Math.round(data.sentiment_coverage_pct);

  return (
    <div data-testid="forecast-health-panel" className="rounded-xl bg-card border border-border p-5">
      <h3 className="text-sm font-medium mb-4">Forecast Health</h3>

      <div className="grid grid-cols-2 gap-4">
        {/* Backtest Accuracy */}
        <div>
          <p className="text-xs text-subtle mb-1">Backtest Accuracy</p>
          <p className={`text-2xl font-semibold font-mono ${healthColor(backtestPct)}`}>
            {backtestPct}%
          </p>
          <p className="text-xs text-subtle mt-1">
            {data.models_passing}/{data.models_total} models
          </p>
        </div>

        {/* Sentiment Coverage */}
        <div>
          <p className="text-xs text-subtle mb-1">Sentiment Coverage</p>
          <p className={`text-2xl font-semibold font-mono ${healthColor(sentimentPct)}`}>
            {sentimentPct}%
          </p>
          <p className="text-xs text-subtle mt-1">
            {data.tickers_with_sentiment}/{data.tickers_total} tickers
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx jest --testPathPattern=forecast-health-panel --no-coverage`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/command-center/forecast-health-panel.tsx frontend/src/__tests__/admin/forecast-health-panel.test.tsx
git commit -m "feat: add ForecastHealthPanel component with tests"
```

---

### Task 3: Wire ForecastHealthPanel into Command Center page

**Files:**
- Modify: `frontend/src/app/(authenticated)/admin/command-center/page.tsx`

- [ ] **Step 1: Add import and wire panel**

In `frontend/src/app/(authenticated)/admin/command-center/page.tsx`:

Add import at line 14 (after PipelinePanel import):
```typescript
import { ForecastHealthPanel } from "@/components/command-center/forecast-health-panel";
```

Add panel to grid at line 76 (after `<PipelinePanel ...>`):
```typescript
          <ForecastHealthPanel data={data?.forecast_health ?? null} />
```

Update LoadingSkeleton count from `4` to `5` at line 19:
```typescript
      {Array.from({ length: 5 }).map((_, i) => (
```

- [ ] **Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(authenticated\)/admin/command-center/page.tsx
git commit -m "feat: wire ForecastHealthPanel into Command Center grid"
```

---

### Task 4: Add System Health drill-down

**Files:**
- Modify: `frontend/src/components/command-center/system-health-panel.tsx`
- Create: `frontend/src/__tests__/admin/system-health-drilldown.test.tsx`

- [ ] **Step 1: Write the tests**

Create `frontend/src/__tests__/admin/system-health-drilldown.test.tsx`:

```typescript
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SystemHealthPanel } from "@/components/command-center/system-health-panel";
import type { SystemHealthZone } from "@/types/command-center";

const MOCK_DATA: SystemHealthZone = {
  status: "healthy",
  database: {
    healthy: true,
    latency_ms: 2.3,
    pool_active: 3,
    pool_size: 10,
    pool_overflow: 0,
    migration_head: "e0f1a2b3c4d5",
  },
  redis: {
    healthy: true,
    latency_ms: 0.8,
    memory_used_mb: 45,
    memory_max_mb: 256,
    total_keys: 1247,
  },
  mcp: {
    healthy: true,
    tool_count: 25,
    mode: "stdio",
    restarts: 0,
    uptime_seconds: 15780,
  },
  celery: {
    workers: 2,
    queued: 0,
    beat_active: true,
  },
  langfuse: {
    connected: true,
    traces_today: 147,
    spans_today: 892,
  },
};

test("renders View Details button", () => {
  render(<SystemHealthPanel data={MOCK_DATA} />);
  expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
});

test("opens drill-down sheet on View Details click", () => {
  render(<SystemHealthPanel data={MOCK_DATA} />);
  fireEvent.click(screen.getByRole("button", { name: /view details/i }));
  expect(screen.getByText("System Health Details")).toBeInTheDocument();
});

test("shows all 5 services with full details in drill-down", () => {
  render(<SystemHealthPanel data={MOCK_DATA} />);
  fireEvent.click(screen.getByRole("button", { name: /view details/i }));
  // Database details
  expect(screen.getByText("e0f1a2b3c4d5")).toBeInTheDocument();
  // Redis details
  expect(screen.getByText(/1,?247/)).toBeInTheDocument();
  // MCP uptime
  expect(screen.getByText(/4h/)).toBeInTheDocument();
  // Celery beat
  expect(screen.getByText(/Active/)).toBeInTheDocument();
  // Langfuse spans
  expect(screen.getByText("892")).toBeInTheDocument();
});

test("shows pool_overflow warning when > 0", () => {
  const data = {
    ...MOCK_DATA,
    database: { ...MOCK_DATA.database, pool_overflow: 3 },
  };
  render(<SystemHealthPanel data={data} />);
  fireEvent.click(screen.getByRole("button", { name: /view details/i }));
  expect(screen.getByText(/3 overflow/)).toBeInTheDocument();
});

test("shows red indicator for unhealthy service", () => {
  const data = {
    ...MOCK_DATA,
    database: { ...MOCK_DATA.database, healthy: false },
  };
  render(<SystemHealthPanel data={data} />);
  fireEvent.click(screen.getByRole("button", { name: /view details/i }));
  const dbSection = screen.getByTestId("drilldown-database");
  expect(dbSection.querySelector("[data-status='down']")).toBeTruthy();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx jest --testPathPattern=system-health-drilldown --no-coverage`
Expected: FAIL — "View Details" button not found

- [ ] **Step 3: Update system-health-panel.tsx with drill-down**

Replace the full content of `frontend/src/components/command-center/system-health-panel.tsx`:

```typescript
"use client";

import { useState } from "react";
import type { SystemHealthZone } from "@/types/command-center";
import { StatusDot } from "./status-dot";
import { DrillDownSheet } from "./drill-down-sheet";

interface SystemHealthPanelProps {
  data: SystemHealthZone | null;
}

function normalizeStatus(s: string): "ok" | "degraded" | "down" | "unknown" {
  const lower = s.toLowerCase();
  if (lower === "ok" || lower === "healthy") return "ok";
  if (lower === "degraded") return "degraded";
  if (lower === "down" || lower === "disabled") return "down";
  return "unknown";
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export function SystemHealthPanel({ data }: SystemHealthPanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);

  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">System Health</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  const overallStatus = normalizeStatus(data.status);

  return (
    <div data-testid="system-health-panel" className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center gap-2 mb-4">
        <StatusDot status={overallStatus} />
        <h3 className="text-sm font-medium">System Health</h3>
        <span className="ml-auto text-xs text-subtle capitalize">{data.status}</span>
      </div>

      <div className="space-y-3">
        {/* Database */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.database.healthy ? "ok" : "down"} size="sm" />
            <span>Database</span>
          </div>
          <span className="font-mono text-subtle">
            {data.database.latency_ms.toFixed(0)}ms
            <span className="ml-2">
              pool {data.database.pool_active}/{data.database.pool_size}
            </span>
          </span>
        </div>

        {/* Redis */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.redis.healthy ? "ok" : "down"} size="sm" />
            <span>Redis</span>
          </div>
          <span className="font-mono text-subtle">
            {data.redis.latency_ms.toFixed(0)}ms
            {data.redis.memory_used_mb != null && (
              <span className="ml-2">{data.redis.memory_used_mb.toFixed(0)}MB</span>
            )}
          </span>
        </div>

        {/* MCP */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.mcp.healthy ? "ok" : "down"} size="sm" />
            <span>MCP</span>
          </div>
          <span className="font-mono text-subtle">
            {data.mcp.tool_count} tools
            <span className="ml-2">{data.mcp.mode}</span>
          </span>
        </div>

        {/* Celery */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot
              status={data.celery.workers != null && data.celery.workers > 0 ? "ok" : "unknown"}
              size="sm"
            />
            <span>Celery</span>
          </div>
          <span className="font-mono text-subtle">
            {data.celery.workers ?? "?"} workers
            {data.celery.queued != null && (
              <span className="ml-2">{data.celery.queued} queued</span>
            )}
          </span>
        </div>

        {/* Langfuse */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={data.langfuse.connected ? "ok" : "down"} size="sm" />
            <span>Langfuse</span>
          </div>
          <span className="font-mono text-subtle">
            {data.langfuse.traces_today} traces
          </span>
        </div>
      </div>

      {/* View Details button */}
      <button
        onClick={() => setDetailOpen(true)}
        aria-expanded={detailOpen}
        className="mt-4 text-xs text-cyan hover:text-cyan/80 transition-colors"
      >
        View Details
      </button>

      {/* Drill-down sheet */}
      <DrillDownSheet
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="System Health Details"
      >
        <div className="space-y-6">
          {/* Database */}
          <div data-testid="drilldown-database" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.database.healthy ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">Database</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Latency: {data.database.latency_ms.toFixed(1)}ms</p>
              <p>
                Connection Pool: {data.database.pool_active}/{data.database.pool_size} active
                {data.database.pool_overflow > 0 && (
                  <span className="text-yellow-400 ml-1">({data.database.pool_overflow} overflow)</span>
                )}
              </p>
              {data.database.migration_head && (
                <p>Migration Head: <code className="font-mono">{data.database.migration_head}</code></p>
              )}
            </div>
          </div>

          {/* Redis */}
          <div data-testid="drilldown-redis" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.redis.healthy ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">Redis</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Latency: {data.redis.latency_ms.toFixed(1)}ms</p>
              <p>
                Memory: {data.redis.memory_used_mb?.toFixed(0) ?? "?"}
                {data.redis.memory_max_mb != null && ` / ${data.redis.memory_max_mb}`} MB
              </p>
              <p>Keys: {data.redis.total_keys?.toLocaleString() ?? "?"}</p>
            </div>
          </div>

          {/* MCP */}
          <div data-testid="drilldown-mcp" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.mcp.healthy ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">MCP Server</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Tools: {data.mcp.tool_count} registered ({data.mcp.mode})</p>
              <p>Uptime: {formatUptime(data.mcp.uptime_seconds)} ({data.mcp.restarts} restarts)</p>
            </div>
          </div>

          {/* Celery */}
          <div data-testid="drilldown-celery" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot
                status={data.celery.workers != null && data.celery.workers > 0 ? "ok" : "unknown"}
                size="sm"
              />
              <span className="text-sm font-medium">Celery</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Workers: {data.celery.workers ?? "?"} | Queued: {data.celery.queued ?? "?"}</p>
              <p>Beat: {data.celery.beat_active ? "Active" : "Inactive"}</p>
            </div>
          </div>

          {/* Langfuse */}
          <div data-testid="drilldown-langfuse" className="space-y-1">
            <div className="flex items-center gap-2">
              <StatusDot status={data.langfuse.connected ? "ok" : "down"} size="sm" />
              <span className="text-sm font-medium">Langfuse</span>
            </div>
            <div className="ml-5 space-y-0.5 text-xs text-subtle">
              <p>Traces Today: {data.langfuse.traces_today}</p>
              <p>Spans Today: {data.langfuse.spans_today}</p>
            </div>
          </div>
        </div>
      </DrillDownSheet>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx jest --testPathPattern=system-health-drilldown --no-coverage`
Expected: PASS (5 tests)

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd frontend && npx jest --no-coverage`
Expected: PASS (all existing tests still pass)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/command-center/system-health-panel.tsx frontend/src/__tests__/admin/system-health-drilldown.test.tsx
git commit -m "feat: add System Health drill-down with full service details"
```

---

### Task 5: Add AuditLog types and hook

**Files:**
- Modify: `frontend/src/types/api.ts` (add types at end)
- Modify: `frontend/src/hooks/use-admin-pipelines.ts` (add hook + query key)

- [ ] **Step 1: Add AuditLog types to api.ts**

Add at end of `frontend/src/types/api.ts`:

```typescript
// Admin Audit Log
export interface AuditLogEntry {
  id: string;
  user_id: string;
  action: string;
  target: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogResponse {
  total: number;
  limit: number;
  offset: number;
  entries: AuditLogEntry[];
}
```

- [ ] **Step 2: Add query key and hook to use-admin-pipelines.ts**

Add to `pipelineKeys` object in `frontend/src/hooks/use-admin-pipelines.ts` (after line 68):
```typescript
  auditLog: (action: string | undefined, limit: number, offset: number) =>
    ["admin-pipelines", "audit-log", action, limit, offset] as const,
```

Add hook at end of file (after `useClearAllCaches`):
```typescript
export function useAuditLog(action?: string, limit = 50, offset = 0) {
  const params = new URLSearchParams();
  if (action) params.set("action", action);
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  return useQuery<AuditLogResponse>({
    queryKey: pipelineKeys.auditLog(action, limit, offset),
    queryFn: () =>
      get<AuditLogResponse>(`/admin/pipelines/audit-log?${params.toString()}`),
    staleTime: 30_000,
  });
}
```

Add import for `AuditLogResponse` type at top of file:
```typescript
import type { AuditLogResponse } from "@/types/api";
```

- [ ] **Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/hooks/use-admin-pipelines.ts
git commit -m "feat: add AuditLog types and useAuditLog hook"
```

---

### Task 6: Create AuditLogTable component with tests

**Files:**
- Create: `frontend/src/components/admin/audit-log-table.tsx`
- Create: `frontend/src/__tests__/admin/audit-log-table.test.tsx`

- [ ] **Step 1: Write the tests**

Create `frontend/src/__tests__/admin/audit-log-table.test.tsx`:

```typescript
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuditLogTable } from "@/components/admin/audit-log-table";

// Mock the hook
jest.mock("@/hooks/use-admin-pipelines", () => ({
  useAuditLog: jest.fn(),
}));

import { useAuditLog } from "@/hooks/use-admin-pipelines";

const mockUseAuditLog = useAuditLog as jest.MockedFunction<typeof useAuditLog>;

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const MOCK_ENTRIES = [
  {
    id: "1",
    user_id: "u1",
    action: "cache_clear",
    target: "signals:*",
    metadata: { keys_deleted: 42 },
    created_at: new Date().toISOString(),
  },
  {
    id: "2",
    user_id: "u1",
    action: "trigger_group",
    target: "nightly",
    metadata: null,
    created_at: new Date(Date.now() - 900_000).toISOString(), // 15 min ago
  },
];

beforeEach(() => {
  mockUseAuditLog.mockReturnValue({
    data: { total: 127, limit: 50, offset: 0, entries: MOCK_ENTRIES },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useAuditLog>);
});

test("renders table with audit entries", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByText("cache_clear")).toBeInTheDocument();
  expect(screen.getByText("signals:*")).toBeInTheDocument();
  expect(screen.getByText("trigger_group")).toBeInTheDocument();
  expect(screen.getByText("nightly")).toBeInTheDocument();
});

test("shows pagination info", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByText(/1-50 of 127/)).toBeInTheDocument();
});

test("prev button disabled on first page", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByRole("button", { name: /prev/i })).toBeDisabled();
});

test("next button navigates to next page", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  const nextBtn = screen.getByRole("button", { name: /next/i });
  expect(nextBtn).not.toBeDisabled();
  fireEvent.click(nextBtn);
  expect(mockUseAuditLog).toHaveBeenCalledWith(undefined, 50, 50);
});

test("renders empty state when no entries", () => {
  mockUseAuditLog.mockReturnValue({
    data: { total: 0, limit: 50, offset: 0, entries: [] },
    isLoading: false,
    error: null,
  } as ReturnType<typeof useAuditLog>);
  render(<AuditLogTable />, { wrapper: Wrapper });
  expect(screen.getByText(/no audit log entries/i)).toBeInTheDocument();
});

test("filter dropdown changes action filter", () => {
  render(<AuditLogTable />, { wrapper: Wrapper });
  const select = screen.getByRole("combobox");
  fireEvent.change(select, { target: { value: "cache_clear" } });
  expect(mockUseAuditLog).toHaveBeenCalledWith("cache_clear", 50, 0);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx jest --testPathPattern=audit-log-table --no-coverage`
Expected: FAIL — module not found

- [ ] **Step 3: Create the component**

Create `frontend/src/components/admin/audit-log-table.tsx`:

```typescript
"use client";

import { useState } from "react";
import { useAuditLog } from "@/hooks/use-admin-pipelines";

const ACTION_OPTIONS = [
  { value: "", label: "All Actions" },
  { value: "trigger_group", label: "Trigger Group" },
  { value: "trigger_task", label: "Trigger Task" },
  { value: "cache_clear", label: "Cache Clear" },
  { value: "cache_clear_all", label: "Cache Clear All" },
];

const PAGE_SIZE = 50;

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function formatMetadata(metadata: Record<string, unknown> | null): string {
  if (!metadata) return "—";
  if ("keys_deleted" in metadata) return `${metadata.keys_deleted} keys`;
  if ("failure_mode" in metadata) return `mode: ${metadata.failure_mode}`;
  return "—";
}

export function AuditLogTable() {
  const [action, setAction] = useState<string | undefined>(undefined);
  const [offset, setOffset] = useState(0);
  const { data, isLoading } = useAuditLog(action, PAGE_SIZE, offset);

  const total = data?.total ?? 0;
  const hasNext = offset + PAGE_SIZE < total;
  const hasPrev = offset > 0;

  return (
    <div className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium">Audit Log</h3>
        <select
          role="combobox"
          value={action ?? ""}
          onChange={(e) => {
            setAction(e.target.value || undefined);
            setOffset(0);
          }}
          className="text-xs bg-card2 border border-border rounded px-2 py-1 text-foreground"
        >
          {ACTION_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p className="text-xs text-subtle">Loading...</p>
      ) : !data?.entries.length ? (
        <p className="text-xs text-subtle py-4 text-center">No audit log entries</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left text-subtle">
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2 pr-4">Action</th>
                  <th className="pb-2 pr-4">Target</th>
                  <th className="pb-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-mono text-subtle">
                      {formatRelativeTime(entry.created_at)}
                    </td>
                    <td className="py-2 pr-4">{entry.action}</td>
                    <td className="py-2 pr-4 font-mono">{entry.target ?? "—"}</td>
                    <td className="py-2 text-subtle">{formatMetadata(entry.metadata)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between mt-3 text-xs text-subtle">
            <span>{offset + 1}-{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={!hasPrev}
                className="px-2 py-1 rounded border border-border disabled:opacity-30"
              >
                Prev
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={!hasNext}
                className="px-2 py-1 rounded border border-border disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx jest --testPathPattern=audit-log-table --no-coverage`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/admin/audit-log-table.tsx frontend/src/__tests__/admin/audit-log-table.test.tsx
git commit -m "feat: add AuditLogTable component with pagination and filtering"
```

---

### Task 7: Wire AuditLogTable into Pipelines page

**Files:**
- Modify: `frontend/src/app/(authenticated)/admin/pipelines/page.tsx`

- [ ] **Step 1: Add import and wire component**

In `frontend/src/app/(authenticated)/admin/pipelines/page.tsx`:

Add import at line 16 (after CacheControls import):
```typescript
import { AuditLogTable } from "@/components/admin/audit-log-table";
```

Add `<AuditLogTable />` after the bottom grid section. Change the grid (lines 107-118) to:
```typescript
          {/* Bottom section: History + Cache Controls side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              {selectedGroup ? (
                <PipelineRunHistory group={selectedGroup} />
              ) : (
                <div className="rounded-lg border border-border bg-card2 px-4 py-8 text-center text-sm text-subtle">
                  Select a group to view run history
                </div>
              )}
            </div>
            <CacheControls />
          </div>

          {/* Audit Log */}
          <AuditLogTable />
```

- [ ] **Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Run all frontend tests**

Run: `cd frontend && npx jest --no-coverage`
Expected: PASS (all tests including 3 new test files)

- [ ] **Step 4: Run lint**

Run: `cd frontend && npm run lint`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(authenticated\)/admin/pipelines/page.tsx
git commit -m "feat: wire AuditLogTable into Pipeline Control page"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 3 features (Forecast Health, System Health Drill-Down, Audit Log) have tasks. Feature 4 (Task Status) explicitly dropped per spec review.
- [x] **No placeholders:** All code blocks are complete, all commands have expected output.
- [x] **Type consistency:** `ForecastHealthZone` interface matches backend schema exactly. `AuditLogEntry`/`AuditLogResponse` match `backend/schemas/admin_pipeline.py:141-159`. `SystemHealthZone` sub-types match `frontend/src/types/command-center.ts:1-45`.
- [x] **Import paths consistent:** All imports use `@/` path aliases per Next.js config.
- [x] **Hard Constraints met:** No backend changes. All hooks use TanStack Query. No `any` types. API paths don't double-prefix.
- [x] **Line count:** ~320 lines estimated across 11 files. Under 500-line limit.
