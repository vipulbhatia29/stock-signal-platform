import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SectorStocksTable } from "@/components/sector-stocks-table";
import type { SectorStock } from "@/types/api";

const mockStocks: SectorStock[] = [
  {
    ticker: "AAPL",
    name: "Apple Inc",
    composite_score: 8.2,
    current_price: 185.5,
    return_pct: 15.3,
    is_held: true,
    is_watched: false,
  },
  {
    ticker: "MSFT",
    name: "Microsoft Corp",
    composite_score: 7.1,
    current_price: 420.0,
    return_pct: 22.1,
    is_held: false,
    is_watched: true,
  },
  {
    ticker: "GOOG",
    name: "Alphabet Inc",
    composite_score: 6.5,
    current_price: 175.0,
    return_pct: 8.4,
    is_held: false,
    is_watched: false,
  },
];

test("renders Your Stocks and Top Sector Stocks sections", () => {
  render(<SectorStocksTable stocks={mockStocks} />);
  expect(screen.getByText("Your Stocks")).toBeInTheDocument();
  expect(screen.getByText("Top Sector Stocks")).toBeInTheDocument();
});

test("renders Held badge for held stocks", () => {
  render(<SectorStocksTable stocks={mockStocks} />);
  expect(screen.getByText("Held")).toBeInTheDocument();
});

test("renders Watched badge for watched stocks", () => {
  render(<SectorStocksTable stocks={mockStocks} />);
  expect(screen.getByText("Watched")).toBeInTheDocument();
});

test("calls onTickerClick when row is clicked", () => {
  const onTickerClick = jest.fn();
  render(<SectorStocksTable stocks={mockStocks} onTickerClick={onTickerClick} />);
  fireEvent.click(screen.getByText("GOOG"));
  expect(onTickerClick).toHaveBeenCalledWith("GOOG");
});

test("shows all ticker names", () => {
  render(<SectorStocksTable stocks={mockStocks} />);
  expect(screen.getByText("AAPL")).toBeInTheDocument();
  expect(screen.getByText("MSFT")).toBeInTheDocument();
  expect(screen.getByText("GOOG")).toBeInTheDocument();
});
