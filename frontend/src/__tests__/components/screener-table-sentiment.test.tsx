import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ScreenerTable } from "@/components/screener-table";
import type { BulkSignalItem } from "@/types/api";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

// Mock density context
jest.mock("@/lib/density-context", () => ({
  useDensity: () => ({ density: "normal" }),
  DensityProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const makeItem = (ticker: string): BulkSignalItem => ({
  ticker,
  name: `${ticker} Inc`,
  sector: "Technology",
  composite_score: 7.5,
  rsi_value: 55,
  rsi_signal: "neutral",
  macd_signal: "bullish",
  sma_signal: "bullish",
  bb_position: "middle",
  annual_return: 0.12,
  volatility: 0.2,
  sharpe_ratio: 1.5,
  computed_at: "2026-04-25",
  is_stale: false,
  price_history: null,
});

function renderTable(sentimentMap?: Map<string, number>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ScreenerTable
        items={[makeItem("AAPL"), makeItem("MSFT"), makeItem("GOOGL")]}
        sortBy="composite_score"
        sortOrder="desc"
        onSort={jest.fn()}
        isLoading={false}
        activeTab="signals"
        onTabChange={jest.fn()}
        sentimentMap={sentimentMap}
      />
    </QueryClientProvider>
  );
}

describe("ScreenerTable sentiment column", () => {
  it("renders sentiment score for tickers in sentiment data", () => {
    const map = new Map([["AAPL", 0.45], ["MSFT", -0.35]]);
    renderTable(map);
    expect(screen.getByText("▲ 0.45")).toBeInTheDocument();
    expect(screen.getByText("▼ -0.35")).toBeInTheDocument();
  });

  it("renders — for tickers not in sentiment data", () => {
    const map = new Map([["AAPL", 0.45]]);
    renderTable(map);
    // MSFT and GOOGL not in map → should show dashes
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("renders neutral styling for sentiment between -0.2 and 0.2", () => {
    const map = new Map([["AAPL", 0.1]]);
    renderTable(map);
    expect(screen.getByText("— 0.10")).toBeInTheDocument();
  });

  it("renders Sentiment column header on signals tab", () => {
    renderTable();
    expect(screen.getByText("Sentiment")).toBeInTheDocument();
  });
});
