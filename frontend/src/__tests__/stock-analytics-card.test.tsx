import React from "react";
import { render, screen } from "@testing-library/react";
import { StockAnalyticsCard } from "@/components/stock-analytics-card";

describe("StockAnalyticsCard", () => {
  it("renders loading skeleton", () => {
    render(<StockAnalyticsCard analytics={undefined} isLoading={true} />);
    expect(screen.getByText("Risk Analytics")).toBeInTheDocument();
  });

  it("renders empty state when no data", () => {
    render(<StockAnalyticsCard analytics={undefined} isLoading={false} />);
    expect(screen.getByText(/not yet available/)).toBeInTheDocument();
  });

  it("renders all null data as empty state", () => {
    render(
      <StockAnalyticsCard
        analytics={{ ticker: "AAPL", sortino: null, max_drawdown: null, alpha: null, beta: null, data_days: null }}
        isLoading={false}
      />
    );
    expect(screen.getByText(/not yet available/)).toBeInTheDocument();
  });

  it("renders metrics when data is available", () => {
    render(
      <StockAnalyticsCard
        analytics={{
          ticker: "AAPL",
          sortino: 1.25,
          max_drawdown: 0.18,
          alpha: 0.03,
          beta: 1.1,
          data_days: 252,
        }}
        isLoading={false}
      />
    );
    expect(screen.getByText("Sortino Ratio")).toBeInTheDocument();
    expect(screen.getByText("1.25")).toBeInTheDocument();
    expect(screen.getByText("Max Drawdown")).toBeInTheDocument();
    expect(screen.getByText("18.00%")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("0.03")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("1.10")).toBeInTheDocument();
  });
});
