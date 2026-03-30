import React from "react";
import { render, screen } from "@testing-library/react";

// jsdom does not provide ResizeObserver
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// Mock lightweight-charts — it requires a real DOM canvas
jest.mock("lightweight-charts", () => ({
  createChart: jest.fn(() => ({
    addSeries: jest.fn(() => ({
      setData: jest.fn(),
    })),
    applyOptions: jest.fn(),
    timeScale: jest.fn(() => ({
      fitContent: jest.fn(),
    })),
    priceScale: jest.fn(() => ({
      applyOptions: jest.fn(),
    })),
    remove: jest.fn(),
    resize: jest.fn(),
  })),
  CandlestickSeries: Symbol("CandlestickSeries"),
  HistogramSeries: Symbol("HistogramSeries"),
}));

// Mock the theme hook
jest.mock("@/lib/lightweight-chart-theme", () => ({
  useLightweightChartTheme: () => ({
    theme: { layout: { background: { color: "#0a0e1a" } } },
    candleColors: { up: "#22c55e", down: "#ef4444" },
  }),
}));

import { createChart } from "lightweight-charts";
import { CandlestickChart } from "@/components/candlestick-chart";
import type { OHLCResponse } from "@/types/api";

const mockOHLC: OHLCResponse = {
  ticker: "AAPL",
  period: "1y",
  count: 3,
  timestamps: ["2025-01-02T00:00:00Z", "2025-01-03T00:00:00Z", "2025-01-06T00:00:00Z"],
  open: [150.0, 152.0, 151.0],
  high: [155.0, 156.0, 154.0],
  low: [149.0, 151.0, 150.0],
  close: [153.0, 154.0, 152.0],
  volume: [1000000, 1200000, 900000],
};

test("renders chart container", () => {
  render(<CandlestickChart data={mockOHLC} />);
  expect(screen.getByTestId("candlestick-container")).toBeInTheDocument();
});

test("calls createChart on mount", () => {
  render(<CandlestickChart data={mockOHLC} />);
  expect(createChart).toHaveBeenCalled();
});

test("renders nothing when data is undefined", () => {
  const { container } = render(<CandlestickChart data={undefined} />);
  expect(container.querySelector("[data-testid='candlestick-container']")).toBeNull();
});
