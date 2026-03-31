import React from "react";
import { render, screen } from "@testing-library/react";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  usePathname: () => "/admin/command-center",
}));

// Mock useCurrentUser
jest.mock("@/hooks/use-current-user", () => ({
  useCurrentUser: () => ({
    isAdmin: true,
    isLoading: false,
    user: { id: 1, username: "admin", role: "admin" },
  }),
}));

// Mock useCommandCenter
const mockData = {
  timestamp: new Date().toISOString(),
  meta: { assembly_ms: 42, degraded_zones: [] },
  system_health: {
    status: "ok",
    database: { healthy: true, latency_ms: 5, pool_active: 2, pool_size: 10, pool_overflow: 0, migration_head: "abc" },
    redis: { healthy: true, latency_ms: 1, memory_used_mb: 32, memory_max_mb: 256, total_keys: 100 },
    mcp: { healthy: true, mode: "stdio", tool_count: 20, restarts: 0, uptime_seconds: 3600 },
    celery: { workers: 2, queued: 0, beat_active: true },
    langfuse: { connected: true, traces_today: 50, spans_today: 200 },
  },
  api_traffic: {
    window_seconds: 300,
    sample_count: 100,
    rps_avg: 12.5,
    latency_p50_ms: 45,
    latency_p95_ms: 120,
    latency_p99_ms: 350,
    error_rate_pct: 0.5,
    total_requests_today: 15000,
    total_errors_today: 75,
    top_endpoints: [{ endpoint: "/api/v1/stocks", count: 500 }],
  },
  llm_operations: {
    tiers: [{ model: "groq-llama", status: "ok", failures_5m: 0, successes_5m: 50, cascade_count: 2, latency: { avg_ms: 800, p95_ms: 1500 } }],
    cost_today_usd: 1.25,
    cost_yesterday_usd: 1.10,
    cost_week_usd: 8.50,
    cascade_rate_pct: 4.0,
    token_budgets: [{ model: "groq-llama", tpm_used_pct: 35, rpm_used_pct: 20 }],
  },
  pipeline: {
    last_run: { started_at: new Date().toISOString(), status: "success", total_duration_seconds: 120, tickers_succeeded: 48, tickers_failed: 2, tickers_total: 50, step_durations: null },
    watermarks: [{ pipeline: "daily_ingest", last_date: "2026-03-31", status: "current" }],
    next_run_at: null,
  },
};

jest.mock("@/hooks/use-command-center", () => ({
  useCommandCenter: () => ({
    data: mockData,
    isLoading: false,
    error: null,
  }),
  useCommandCenterDrillDown: () => ({
    data: null,
    isFetching: false,
    refetch: jest.fn(),
  }),
  commandCenterKeys: {
    aggregate: ["command-center"],
    drillDown: (zone: string) => ["command-center", zone],
  },
}));

// Mock motion-primitives
jest.mock("@/components/motion-primitives", () => ({
  PageTransition: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

// Mock skeleton
jest.mock("@/components/ui/skeleton", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={className} />
  ),
}));

import CommandCenterPage from "@/app/(authenticated)/admin/command-center/page";

test("renders command center page with all zones", () => {
  render(<CommandCenterPage />);
  expect(screen.getByText("Command Center")).toBeInTheDocument();
  expect(screen.getByText("Platform operations overview")).toBeInTheDocument();
});

test("renders system health panel", () => {
  render(<CommandCenterPage />);
  expect(screen.getByTestId("system-health-panel")).toBeInTheDocument();
});

test("renders api traffic panel", () => {
  render(<CommandCenterPage />);
  expect(screen.getByTestId("api-traffic-panel")).toBeInTheDocument();
});

test("renders llm operations panel", () => {
  render(<CommandCenterPage />);
  expect(screen.getByTestId("llm-operations-panel")).toBeInTheDocument();
});

test("renders pipeline panel", () => {
  render(<CommandCenterPage />);
  expect(screen.getByTestId("pipeline-panel")).toBeInTheDocument();
});
