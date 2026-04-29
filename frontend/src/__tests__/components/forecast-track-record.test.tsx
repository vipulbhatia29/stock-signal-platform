import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ForecastTrackRecord } from "@/components/forecast-track-record";

const mockTrackRecord = {
  data: {
    ticker: "AAPL",
    evaluations: [
      {
        forecast_date: "2026-01-01",
        target_date: "2026-04-01",
        horizon_days: 90,
        expected_return_pct: 3.2,
        return_lower_pct: -1.5,
        return_upper_pct: 8.0,
        actual_return_pct: 2.8,
        error_pct: 0.4,
        direction_correct: true,
      },
      {
        forecast_date: "2026-01-15",
        target_date: "2026-04-15",
        horizon_days: 90,
        expected_return_pct: 4.1,
        return_lower_pct: -0.8,
        return_upper_pct: 9.0,
        actual_return_pct: 5.2,
        error_pct: 1.1,
        direction_correct: true,
      },
    ],
    summary: {
      total_evaluated: 2,
      direction_hit_rate: 1.0,
      avg_error_pct: 0.0154, // decimal fraction — displayed as 1.5%
      ci_containment_rate: 1.0,
    },
  },
  isLoading: false,
  isError: false,
  refetch: jest.fn(),
};

jest.mock("@/hooks/use-forecasts", () => ({
  ...jest.requireActual("@/hooks/use-forecasts"),
  useForecastTrackRecord: () => mockTrackRecord,
}));

// Mock Recharts to avoid canvas issues in jsdom
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

describe("ForecastTrackRecord", () => {
  it("renders summary KPI tiles", () => {
    render(<ForecastTrackRecord ticker="AAPL" />, { wrapper });
    expect(screen.getByText("2")).toBeInTheDocument(); // total evaluated
    // Both direction hit and CI hit are 100% — verify both exist
    expect(screen.getAllByText("100%")).toHaveLength(2);
    expect(screen.getByText("1.5%")).toBeInTheDocument(); // avg error
    expect(screen.getByText("Direction Hit")).toBeInTheDocument();
    expect(screen.getByText("CI Hit")).toBeInTheDocument();
  });

  it("shows empty state when no evaluations", () => {
    const origData = mockTrackRecord.data;
    mockTrackRecord.data = {
      ...origData,
      evaluations: [],
      summary: { total_evaluated: 0, direction_hit_rate: 0, avg_error_pct: 0, ci_containment_rate: 0 },
    };
    render(<ForecastTrackRecord ticker="AAPL" />, { wrapper });
    expect(screen.getByText(/no evaluated forecasts/i)).toBeInTheDocument();
    mockTrackRecord.data = origData;
  });
});
