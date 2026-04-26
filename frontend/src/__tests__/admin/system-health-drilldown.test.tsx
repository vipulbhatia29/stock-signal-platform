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
  expect(screen.getByText("e0f1a2b3c4d5")).toBeInTheDocument();
  expect(screen.getByText(/1,?247/)).toBeInTheDocument();
  expect(screen.getByText(/4h/)).toBeInTheDocument();
  expect(screen.getByText(/Active/)).toBeInTheDocument();
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
  // StatusDot renders bg-red-500 for "down" status
  expect(dbSection.querySelector(".bg-red-500")).toBeTruthy();
});
