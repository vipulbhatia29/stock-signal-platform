import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CostBreakdown } from "@/app/(authenticated)/admin/observability/_components/cost-breakdown";
import * as adminHooks from "@/hooks/use-admin-observability";
import type { AdminCostsEnvelope } from "@/types/admin-observability";

jest.mock("@/hooks/use-admin-observability");
jest.mock("@/lib/chart-theme", () => ({
  useChartColors: () => ({
    price: "#38bdf8",
    chart1: "#7c3aed",
    chart2: "#06b6d4",
    chart3: "#22d3a0",
  }),
  CHART_STYLE: { grid: {}, axis: {} },
}));
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="chart-container">{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
}));

const MOCK_ENVELOPE: AdminCostsEnvelope = {
  tool: "get_cost_breakdown",
  window: { from: "2026-04-17T00:00:00Z", to: "2026-04-24T00:00:00Z" },
  result: {
    by: "provider",
    groups: [
      {
        provider: "openai",
        total_cost_usd: 4.5678,
        call_count: 300,
        avg_cost_per_call: 0.01523,
        p95_latency_ms: 1500,
      },
      {
        provider: "anthropic",
        total_cost_usd: 2.1234,
        call_count: 150,
        avg_cost_per_call: 0.01416,
        p95_latency_ms: 1200,
      },
    ],
  },
  meta: { total_count: 2, truncated: false, schema_version: "1.0" },
};

const LOADING_RESULT = { data: undefined, isLoading: true, error: null };
const ERROR_RESULT = { data: undefined, isLoading: false, error: new Error("Network error") };
const SUCCESS_RESULT = { data: MOCK_ENVELOPE, isLoading: false, error: null };

const onOpenTrace = jest.fn();

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(QueryClientProvider, { client: qc }, ui)
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  (adminHooks.useAdminCosts as jest.Mock).mockReturnValue(SUCCESS_RESULT);
});

describe("CostBreakdown", () => {
  it("renders the section heading", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText("Cost Breakdown")).toBeInTheDocument();
  });

  it("renders by-dimension toggle buttons", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText("Provider")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Tier")).toBeInTheDocument();
    expect(screen.getByText("User")).toBeInTheDocument();
  });

  it("renders window selector buttons", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText("7d")).toBeInTheDocument();
    expect(screen.getByText("30d")).toBeInTheDocument();
  });

  it("renders chart container on success", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByTestId("chart-container")).toBeInTheDocument();
  });

  it("renders table with provider rows", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("anthropic")).toBeInTheDocument();
  });

  it("shows loading skeletons when fetching", () => {
    (adminHooks.useAdminCosts as jest.Mock).mockReturnValue(LOADING_RESULT);
    const { container } = wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    const skeletons = container.querySelectorAll("[data-slot='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error card on fetch failure", () => {
    (adminHooks.useAdminCosts as jest.Mock).mockReturnValue(ERROR_RESULT);
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText(/Failed to load cost data/)).toBeInTheDocument();
  });

  it("calls useAdminCosts with default params", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(adminHooks.useAdminCosts).toHaveBeenCalledWith("7d", "provider", 50);
  });

  it("switches dimension to model on button click", async () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    await userEvent.click(screen.getByText("Model"));
    expect(adminHooks.useAdminCosts).toHaveBeenCalledWith("7d", "model", 50);
  });

  it("switches window to 30d on button click", async () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    await userEvent.click(screen.getByText("30d"));
    expect(adminHooks.useAdminCosts).toHaveBeenCalledWith("30d", "provider", 50);
  });

  it("shows 'no cost data' when groups is empty", () => {
    const emptyEnvelope: AdminCostsEnvelope = {
      ...MOCK_ENVELOPE,
      result: { by: "provider", groups: [] },
    };
    (adminHooks.useAdminCosts as jest.Mock).mockReturnValue({
      data: emptyEnvelope,
      isLoading: false,
      error: null,
    });
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText("No cost data available.")).toBeInTheDocument();
  });

  it("renders top-10 table heading with dimension name", () => {
    wrap(<CostBreakdown onOpenTrace={onOpenTrace} />);
    expect(screen.getByText(/Top 10 by Cost — grouped by provider/)).toBeInTheDocument();
  });
});
