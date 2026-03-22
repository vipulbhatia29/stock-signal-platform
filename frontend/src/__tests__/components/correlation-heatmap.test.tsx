import React from "react";
import { render, screen } from "@testing-library/react";
import { CorrelationHeatmap } from "@/components/correlation-heatmap";

const tickers = ["AAPL", "MSFT", "GOOG"];
const matrix = [
  [1.0, 0.85, 0.42],
  [0.85, 1.0, 0.65],
  [0.42, 0.65, 1.0],
];

test("renders all ticker labels", () => {
  render(<CorrelationHeatmap tickers={tickers} matrix={matrix} />);
  // Each ticker appears as row and column header
  const aaplElements = screen.getAllByText("AAPL");
  expect(aaplElements.length).toBeGreaterThanOrEqual(2);
});

test("renders diagonal as 1.0", () => {
  render(<CorrelationHeatmap tickers={tickers} matrix={matrix} />);
  const ones = screen.getAllByText("1.0");
  expect(ones.length).toBe(3); // 3x3 diagonal
});

test("renders off-diagonal values", () => {
  render(<CorrelationHeatmap tickers={tickers} matrix={matrix} />);
  const highCorr = screen.getAllByText("0.85");
  expect(highCorr.length).toBe(2); // symmetric: [0,1] and [1,0]
});

test("renders color legend", () => {
  render(<CorrelationHeatmap tickers={tickers} matrix={matrix} />);
  expect(screen.getByText(/Low/)).toBeInTheDocument();
  expect(screen.getByText(/Moderate/)).toBeInTheDocument();
  expect(screen.getByText(/High/)).toBeInTheDocument();
});
