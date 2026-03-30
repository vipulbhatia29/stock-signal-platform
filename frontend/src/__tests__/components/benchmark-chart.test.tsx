import React from "react";
import { render, screen } from "@testing-library/react";
import { BenchmarkChart } from "@/components/benchmark-chart";
import type { BenchmarkDataPoint } from "@/hooks/use-stocks";

// Mock Recharts — jsdom doesn't have SVG layout engine
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: React.PropsWithChildren) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="line" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  CartesianGrid: () => <div />,
}));

const mockData: BenchmarkDataPoint[] = [
  { date: "2025-01-02", AAPL: 0, "S&P 500": 0, "NASDAQ Composite": 0 },
  { date: "2025-06-15", AAPL: 15.2, "S&P 500": 8.1, "NASDAQ Composite": 12.3 },
  { date: "2025-12-31", AAPL: 25.3, "S&P 500": 14.5, "NASDAQ Composite": 18.7 },
];

test("renders chart container when data is present", () => {
  render(
    <BenchmarkChart data={mockData} isLoading={false} seriesNames={["AAPL", "S&P 500", "NASDAQ Composite"]} />
  );
  expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
});

test("renders section heading", () => {
  render(
    <BenchmarkChart data={mockData} isLoading={false} seriesNames={["AAPL"]} />
  );
  expect(screen.getByText(/benchmark/i)).toBeInTheDocument();
});

test("renders loading skeleton", () => {
  const { container } = render(
    <BenchmarkChart data={undefined} isLoading={true} seriesNames={[]} />
  );
  expect(container.querySelectorAll("[data-slot='skeleton']").length).toBeGreaterThan(0);
});

test("renders error state with retry", () => {
  const onRetry = jest.fn();
  render(
    <BenchmarkChart
      data={undefined}
      isLoading={false}
      isError={true}
      onRetry={onRetry}
      seriesNames={[]}
    />
  );
  expect(screen.getByText(/try again/i)).toBeInTheDocument();
});

test("renders empty state when no data", () => {
  render(
    <BenchmarkChart data={[]} isLoading={false} seriesNames={[]} />
  );
  expect(screen.getByText(/no benchmark data/i)).toBeInTheDocument();
});
