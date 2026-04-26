import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConvergenceCard } from "@/components/convergence-card";

// Mock hooks
const mockConvergence = {
  data: {
    ticker: "AAPL",
    date: "2026-04-25",
    signals: [
      { signal: "rsi", direction: "bullish", value: 42.1 },
      { signal: "macd", direction: "bullish", value: 0.03 },
      { signal: "sma", direction: "bearish", value: null },
      { signal: "piotroski", direction: "bullish", value: 7 },
      { signal: "forecast", direction: "bullish", value: null },
      { signal: "news", direction: "neutral", value: null },
    ],
    signals_aligned: 4,
    convergence_label: "weak_bull",
    composite_score: 7.2,
    divergence: {
      is_divergent: false,
      forecast_direction: null,
      technical_majority: null,
      historical_hit_rate: null,
      sample_count: null,
    },
    rationale: "4 of 6 signals lean bullish",
  },
  isLoading: false,
  isError: false,
  refetch: jest.fn(),
};

const mockHistory = {
  data: {
    ticker: "AAPL",
    data: [
      { date: "2026-04-20", convergence_label: "mixed", signals_aligned: 3, composite_score: 5.0, actual_return_90d: null, actual_return_180d: null },
      { date: "2026-04-25", convergence_label: "weak_bull", signals_aligned: 4, composite_score: 7.2, actual_return_90d: null, actual_return_180d: null },
    ],
    total: 2,
    limit: 50,
    offset: 0,
  },
  isLoading: false,
};

jest.mock("@/hooks/use-convergence", () => ({
  useStockConvergence: () => mockConvergence,
  useConvergenceHistory: () => mockHistory,
}));

jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("ConvergenceCard", () => {
  it("renders convergence label and signal count", () => {
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/weak.bull/i)).toBeInTheDocument();
    expect(screen.getByText("4 of 6 signals bullish")).toBeInTheDocument();
  });

  it("renders individual signal directions", () => {
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/RSI/i)).toBeInTheDocument();
    expect(screen.getByText(/MACD/i)).toBeInTheDocument();
  });

  it("hides divergence alert when not divergent", () => {
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.queryByText(/divergence/i)).not.toBeInTheDocument();
  });

  it("shows divergence alert when divergent", () => {
    (mockConvergence.data.divergence as Record<string, unknown>) = {
      is_divergent: true,
      forecast_direction: "bullish",
      technical_majority: "bearish",
      historical_hit_rate: 0.68,
      sample_count: 22,
    };
    render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/divergence/i)).toBeInTheDocument();
    expect(screen.getByText(/68%/)).toBeInTheDocument();
    // Reset
    mockConvergence.data.divergence = {
      is_divergent: false,
      forecast_direction: null,
      technical_majority: null,
      historical_hit_rate: null,
      sample_count: null,
    };
  });

  it("returns null when no data", () => {
    const orig = mockConvergence.data;
    // @ts-expect-error — testing null data
    mockConvergence.data = undefined;
    const { container } = render(<ConvergenceCard ticker="AAPL" />, { wrapper });
    expect(container.firstChild).toBeNull();
    mockConvergence.data = orig;
  });
});
