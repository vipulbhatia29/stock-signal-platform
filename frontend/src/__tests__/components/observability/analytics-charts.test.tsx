import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnalyticsCharts } from "@/app/(authenticated)/observability/_components/analytics-charts";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: jest.fn() }),
  usePathname: () => "/observability",
}));
jest.mock("@/hooks/use-observability");
jest.mock("@/lib/chart-theme", () => ({
  useChartColors: () => ({
    price: "#38bdf8",
    sma200: "#a78bfa",
    gain: "#22d3a0",
    loss: "#f87171",
  }),
  CHART_STYLE: { grid: {}, axis: {} },
}));
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="chart-container">{children}</div>
  ),
  ComposedChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="composed-chart">{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Line: () => <div />,
  Bar: () => <div />,
  Area: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
}));

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    React.createElement(QueryClientProvider, { client: qc }, ui),
  );
}

describe("AnalyticsCharts", () => {
  beforeEach(() => {
    (obsHooks.useObservabilityGrouped as jest.Mock).mockReturnValue({
      data: {
        group_by: "date",
        bucket: "day",
        groups: [
          {
            key: "2026-03-30",
            query_count: 10,
            total_cost_usd: 0.05,
            avg_cost_usd: 0.005,
            avg_latency_ms: 1200,
            error_rate: 0.1,
          },
          {
            key: "2026-03-31",
            query_count: 15,
            total_cost_usd: 0.08,
            avg_cost_usd: 0.005,
            avg_latency_ms: 1100,
            error_rate: 0.05,
          },
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

  it("renders chart container", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.getByTestId("chart-container")).toBeInTheDocument();
  });

  it("shows empty state when no data", () => {
    (obsHooks.useObservabilityGrouped as jest.Mock).mockReturnValue({
      data: { group_by: "date", bucket: "day", groups: [], total_queries: 0 },
      isLoading: false,
    });
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    expect(screen.getByText("Not enough data to show trends")).toBeInTheDocument();
  });

  it("renders date range selector pills", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.getByText("7d")).toBeInTheDocument();
    expect(screen.getByText("30d")).toBeInTheDocument();
    expect(screen.getByText("90d")).toBeInTheDocument();
  });

  it("renders bucket selector for date dimension", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(screen.getByText("day")).toBeInTheDocument();
    expect(screen.getByText("week")).toBeInTheDocument();
    expect(screen.getByText("month")).toBeInTheDocument();
  });

  it("passes date_from to the grouped hook", () => {
    wrap(<AnalyticsCharts isAdmin={false} />);
    expect(obsHooks.useObservabilityGrouped).toHaveBeenCalledWith(
      expect.objectContaining({
        group_by: "date",
        bucket: "day",
        date_from: expect.any(String),
      }),
    );
  });
});
