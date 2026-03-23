import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TrendingStocks } from "@/components/trending-stocks";

// Mock the hook
jest.mock("@/hooks/use-stocks", () => ({
  useTrendingStocks: jest.fn(),
}));

import { useTrendingStocks } from "@/hooks/use-stocks";
const mockUseTrending = useTrendingStocks as jest.MockedFunction<typeof useTrendingStocks>;

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("TrendingStocks", () => {
  it("renders trending stocks with scores", () => {
    mockUseTrending.mockReturnValue({
      data: {
        total: 2,
        items: [
          {
            ticker: "PLTR",
            name: "Palantir",
            sector: "Technology",
            composite_score: 8.5,
            rsi_value: 55,
            rsi_signal: "neutral",
            macd_signal: "bullish",
            sma_signal: "bullish",
            bb_position: "middle",
            annual_return: 0.25,
            volatility: 0.35,
            sharpe_ratio: 0.71,
            computed_at: "2026-03-20T12:00:00Z",
            is_stale: false,
            price_history: [100, 105, 110],
          },
          {
            ticker: "NVDA",
            name: "NVIDIA",
            sector: "Technology",
            composite_score: 7.8,
            rsi_value: 60,
            rsi_signal: "neutral",
            macd_signal: "bullish",
            sma_signal: "bullish",
            bb_position: "upper",
            annual_return: 0.40,
            volatility: 0.45,
            sharpe_ratio: 0.89,
            computed_at: "2026-03-20T12:00:00Z",
            is_stale: false,
            price_history: [200, 210, 220],
          },
        ],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useTrendingStocks>);

    renderWithQuery(<TrendingStocks />);
    expect(screen.getByText("PLTR")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("8.5/10")).toBeInTheDocument();
  });

  it("returns null when no data", () => {
    mockUseTrending.mockReturnValue({
      data: { total: 0, items: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof useTrendingStocks>);

    const { container } = renderWithQuery(<TrendingStocks />);
    expect(container.firstChild).toBeNull();
  });
});
