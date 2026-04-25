import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DqScanner } from "@/app/(authenticated)/admin/observability/_components/dq-scanner";

jest.mock("@/hooks/use-admin-observability", () => ({
  useAdminDq: jest.fn(),
}));

import { useAdminDq } from "@/hooks/use-admin-observability";
const mockUseAdminDq = useAdminDq as jest.MockedFunction<typeof useAdminDq>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_DATA = {
  tool: "get_dq_findings",
  window: { from: "2026-04-23T00:00:00Z", to: "2026-04-24T00:00:00Z" },
  result: {
    findings: [
      {
        check_name: "missing_prices",
        severity: "critical",
        ticker: "AAPL",
        message: "No price data for last 3 days",
        metadata: null,
        detected_at: new Date(Date.now() - 600_000).toISOString(),
      },
      {
        check_name: "stale_signals",
        severity: "warning",
        ticker: null,
        message: "15 tickers have signals older than 48h",
        metadata: null,
        detected_at: new Date(Date.now() - 7200_000).toISOString(),
      },
    ],
  },
  meta: { total_count: 2, truncated: false, schema_version: "v1" },
};

test("renders findings with severity badges", () => {
  mockUseAdminDq.mockReturnValue({
    data: MOCK_DATA,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  expect(screen.getByText("missing_prices")).toBeInTheDocument();
  expect(screen.getByText("critical")).toBeInTheDocument();
  expect(screen.getByText("stale_signals")).toBeInTheDocument();
  expect(screen.getByText("warning")).toBeInTheDocument();
});

test("renders ticker when present", () => {
  mockUseAdminDq.mockReturnValue({
    data: MOCK_DATA,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  expect(screen.getByText("Ticker: AAPL")).toBeInTheDocument();
});

test("renders loading skeletons", () => {
  mockUseAdminDq.mockReturnValue({
    data: undefined,
    isLoading: true,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  expect(screen.queryByText("missing_prices")).not.toBeInTheDocument();
});

test("renders error state", () => {
  mockUseAdminDq.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: new Error("fail"),
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  expect(screen.getByText(/Failed to load DQ data/)).toBeInTheDocument();
});

test("renders empty state when no findings", () => {
  mockUseAdminDq.mockReturnValue({
    data: { ...MOCK_DATA, result: { findings: [] } },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  expect(screen.getByText(/No DQ findings/)).toBeInTheDocument();
});

test("renders disabled Run Now button", () => {
  mockUseAdminDq.mockReturnValue({
    data: MOCK_DATA,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  const btn = screen.getByRole("button", { name: "Run Now" });
  expect(btn).toBeDisabled();
});

test("renders summary count", () => {
  mockUseAdminDq.mockReturnValue({
    data: MOCK_DATA,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  expect(screen.getByText("2 findings in last 24h")).toBeInTheDocument();
});

test("time range buttons change filter", async () => {
  mockUseAdminDq.mockReturnValue({
    data: MOCK_DATA,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminDq>);

  render(<DqScanner />, { wrapper });
  await userEvent.click(screen.getByRole("button", { name: "7d" }));
  // After click, the hook should be called with since: "7d"
  expect(mockUseAdminDq).toHaveBeenCalledWith(
    expect.objectContaining({ since: "7d" })
  );
});
