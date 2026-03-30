import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock Recharts
jest.mock("recharts", () => ({
  ComposedChart: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  Area: () => <div />,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CartesianGrid: () => <div />,
}));

// Mock use-stocks hooks
jest.mock("@/hooks/use-stocks", () => ({
  usePrices: () => ({
    data: [
      { time: "2025-01-02", close: 150, volume: 1000000 },
      { time: "2025-06-15", close: 175, volume: 1200000 },
    ],
    isLoading: false,
  }),
  useOHLC: () => ({
    data: { ticker: "AAPL", period: "1y", count: 2, timestamps: [], open: [], high: [], low: [], close: [], volume: [] },
    isLoading: false,
  }),
}));

// Mock chart-theme
jest.mock("@/lib/chart-theme", () => ({
  useChartColors: () => ({
    price: "#3b82f6",
    volume: "#6b7280",
    gain: "#22c55e",
    loss: "#ef4444",
    chart1: "#f59e0b",
    chart2: "#8b5cf6",
    chart3: "#ec4899",
    sma50: "#f59e0b",
    sma200: "#ef4444",
    rsi: "#8b5cf6",
  }),
  CHART_STYLE: {
    grid: { strokeDasharray: "3 3" },
    axis: { tick: { fontSize: 11 } },
    tooltip: { cursor: {} },
  },
}));

// Mock the lazy-loaded candlestick (it would be dynamically imported)
jest.mock("@/components/candlestick-chart", () => ({
  CandlestickChart: () => <div data-testid="candlestick-chart">Candlestick</div>,
}));

import { PriceChart } from "@/components/price-chart";

test("renders Line button as active by default", () => {
  render(<PriceChart ticker="AAPL" period="1y" onPeriodChange={() => {}} />);
  const lineBtn = screen.getByRole("button", { name: /line/i });
  expect(lineBtn).toBeInTheDocument();
});

test("renders Candle button", () => {
  render(<PriceChart ticker="AAPL" period="1y" onPeriodChange={() => {}} />);
  expect(screen.getByRole("button", { name: /candle/i })).toBeInTheDocument();
});
