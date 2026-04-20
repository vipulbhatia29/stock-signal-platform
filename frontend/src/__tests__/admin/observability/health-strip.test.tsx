import React from "react";
import { render, screen } from "@testing-library/react";
import { HealthStrip } from "@/app/(authenticated)/admin/observability/_components/health-strip";
import type { AdminKpisResult } from "@/types/admin-observability";

const MOCK_DATA: AdminKpisResult = {
  overall_status: "healthy",
  subsystems: {
    http: { status: "healthy", total_requests: 150, error_count: 3 },
    db: { status: "degraded" },
    celery: { status: "healthy", worker_count: 4 },
    external_api: {
      status: "failing",
      providers: { yfinance: {}, openai: {} },
    },
  },
};

test("renders subsystem pills for each entry", () => {
  render(<HealthStrip data={MOCK_DATA} isLoading={false} error={null} />);
  expect(screen.getByText("HTTP")).toBeInTheDocument();
  expect(screen.getByText("Database")).toBeInTheDocument();
  expect(screen.getByText("Celery")).toBeInTheDocument();
  expect(screen.getByText("External API")).toBeInTheDocument();
});

test("renders correct status dots", () => {
  render(<HealthStrip data={MOCK_DATA} isLoading={false} error={null} />);
  const dots = screen.getAllByTestId("status-dot");
  expect(dots).toHaveLength(4);
  // HTTP = healthy = emerald
  expect(dots[0].className).toContain("bg-emerald-400");
  // DB = degraded = yellow
  expect(dots[1].className).toContain("bg-yellow-400");
  // Celery = healthy = emerald
  expect(dots[2].className).toContain("bg-emerald-400");
  // External API = failing = red
  expect(dots[3].className).toContain("bg-red-500");
});

test("shows loading skeletons when isLoading is true", () => {
  const { container } = render(
    <HealthStrip data={undefined} isLoading={true} error={null} />
  );
  // 7 skeleton elements
  const skeletons = container.querySelectorAll("[data-slot='skeleton']");
  expect(skeletons.length).toBe(7);
});

test("shows error banner on error", () => {
  render(
    <HealthStrip
      data={undefined}
      isLoading={false}
      error={new Error("Network error")}
    />
  );
  expect(
    screen.getByText(/Failed to load system health/)
  ).toBeInTheDocument();
});

test("renders nothing when data is undefined and not loading", () => {
  const { container } = render(
    <HealthStrip data={undefined} isLoading={false} error={null} />
  );
  expect(container.textContent).toBe("");
});

test("shows message when subsystems object is empty", () => {
  const emptyData: AdminKpisResult = {
    overall_status: "healthy",
    subsystems: {},
  };
  render(<HealthStrip data={emptyData} isLoading={false} error={null} />);
  expect(screen.getByText(/No subsystem data available/)).toBeInTheDocument();
});

test("displays one-line stat for HTTP subsystem", () => {
  render(<HealthStrip data={MOCK_DATA} isLoading={false} error={null} />);
  expect(screen.getByText("150 req, 3 err")).toBeInTheDocument();
});

test("displays worker count for Celery subsystem", () => {
  render(<HealthStrip data={MOCK_DATA} isLoading={false} error={null} />);
  expect(screen.getByText("4 workers")).toBeInTheDocument();
});

test("displays provider count for External API subsystem", () => {
  render(<HealthStrip data={MOCK_DATA} isLoading={false} error={null} />);
  expect(screen.getByText("2 providers")).toBeInTheDocument();
});
