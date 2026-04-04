import React from "react";
import { render, screen } from "@testing-library/react";
import { MonteCarloChart } from "@/components/portfolio/monte-carlo-chart";
import type { MonteCarloSummary } from "@/types/api";

// Mock Recharts — jsdom has no layout engine, ResponsiveContainer breaks without this.
jest.mock("recharts", () => ({
  AreaChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="area-chart">{children}</div>
  ),
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

// Mock chart theme hooks — pure rendering, no theme needed.
jest.mock("@/lib/chart-theme", () => ({
  useChartColors: () => ({ chart1: "#4f46e5" }),
  CHART_STYLE: {
    grid: { strokeDasharray: "3 3", className: "" },
    axis: { className: "" },
  },
}));

// Mock formatCurrency for stable output.
jest.mock("@/lib/format", () => ({
  formatCurrency: (v: number) => `$${v.toLocaleString()}`,
}));

const MOCK_MC: MonteCarloSummary = {
  simulation_days: 90,
  initial_value: 100000,
  terminal_median: 103200,
  terminal_p5: 88500,
  terminal_p95: 118900,
  bands: {
    p5: [100000, 97000, 94000, 88500],
    p25: [100000, 99000, 98000, 96500],
    p50: [100000, 101000, 102000, 103200],
    p75: [100000, 103000, 106000, 110000],
    p95: [100000, 106000, 112000, 118900],
  },
};

describe("MonteCarloChart", () => {
  it("renders loading skeleton when isLoading is true", () => {
    /** Skeleton placeholder renders with animate-pulse while data loads. */
    const { container } = render(
      <MonteCarloChart data={undefined} isLoading={true} />,
    );
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("renders empty-state message when data is undefined and not loading", () => {
    /** Shows fallback message when API returns no simulation data. */
    render(<MonteCarloChart data={undefined} isLoading={false} />);
    expect(screen.getByText("No simulation data available.")).toBeInTheDocument();
  });

  it("renders empty-state message when bands.p50 is empty array", () => {
    /** Empty band arrays are treated as missing data and show the fallback message. */
    const emptyBands: MonteCarloSummary = {
      ...MOCK_MC,
      bands: { p5: [], p25: [], p50: [], p75: [], p95: [] },
    };
    render(<MonteCarloChart data={emptyBands} isLoading={false} />);
    expect(screen.getByText("No simulation data available.")).toBeInTheDocument();
  });

  it("renders chart when data has simulation bands", () => {
    /** Full data renders the area chart without any fallback message. */
    render(<MonteCarloChart data={MOCK_MC} isLoading={false} />);
    expect(screen.queryByText("No simulation data available.")).not.toBeInTheDocument();
    expect(screen.getByTestId("area-chart")).toBeInTheDocument();
  });

  it("shows simulation horizon and initial value metadata", () => {
    /** Metadata row shows the configured horizon days and initial portfolio value. */
    render(<MonteCarloChart data={MOCK_MC} isLoading={false} />);
    expect(screen.getByText(/90-day horizon/)).toBeInTheDocument();
  });

  it("shows worst-5-percent and best-5-percent terminal values", () => {
    /** Terminal value summary shows both tail outcomes for user context. */
    render(<MonteCarloChart data={MOCK_MC} isLoading={false} />);
    expect(screen.getByText(/Worst 5%/)).toBeInTheDocument();
    expect(screen.getByText(/Best 5%/)).toBeInTheDocument();
  });
});
