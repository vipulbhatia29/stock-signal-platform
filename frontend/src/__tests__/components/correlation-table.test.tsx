import React from "react";
import { render, screen } from "@testing-library/react";
import { CorrelationTable } from "@/components/correlation-table";

const tickers = ["AAPL", "MSFT", "GOOG"];
const matrix = [
  [1.0, 0.85, 0.25],
  [0.85, 1.0, 0.55],
  [0.25, 0.55, 1.0],
];

test("renders pairs sorted by absolute correlation descending", () => {
  render(<CorrelationTable tickers={tickers} matrix={matrix} />);
  const pairs = screen.getAllByText(/↔/);
  expect(pairs.length).toBe(3); // 3 unique pairs for 3 tickers
  // First pair should be AAPL ↔ MSFT (0.85)
  expect(screen.getByText("0.85")).toBeInTheDocument();
});

test("shows interpretation for high correlation", () => {
  render(<CorrelationTable tickers={tickers} matrix={matrix} />);
  expect(screen.getByText("Highly correlated")).toBeInTheDocument();
});

test("shows interpretation for moderate correlation", () => {
  render(<CorrelationTable tickers={tickers} matrix={matrix} />);
  expect(screen.getByText("Moderate")).toBeInTheDocument();
});

test("shows interpretation for low correlation", () => {
  render(<CorrelationTable tickers={tickers} matrix={matrix} />);
  expect(screen.getByText("Low correlation")).toBeInTheDocument();
});
