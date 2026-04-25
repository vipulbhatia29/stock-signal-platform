import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PipelineHealth } from "@/app/(authenticated)/admin/observability/_components/pipeline-health";

// Mock the hook
jest.mock("@/hooks/use-admin-observability", () => ({
  useAdminPipelines: jest.fn(),
}));

import { useAdminPipelines } from "@/hooks/use-admin-observability";
const mockUseAdminPipelines = useAdminPipelines as jest.MockedFunction<typeof useAdminPipelines>;

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const MOCK_RESULT = {
  tool: "diagnose_pipeline",
  window: { from: "2026-04-24T00:00:00Z", to: "2026-04-24T01:00:00Z" },
  result: {
    pipeline_name: "nightly_price_refresh",
    runs: [
      {
        id: "run-1",
        pipeline_name: "nightly_price_refresh",
        started_at: new Date(Date.now() - 3600_000).toISOString(),
        completed_at: new Date(Date.now() - 3000_000).toISOString(),
        status: "success",
        tickers_total: 100,
        tickers_succeeded: 98,
        tickers_failed: 2,
        error_summary: null,
        step_durations: { fetch: 120, compute: 80 },
        total_duration_seconds: 200,
        retry_count: 0,
      },
    ],
    watermark: {
      pipeline_name: "nightly_price_refresh",
      last_completed_date: "2026-04-24",
      last_completed_at: new Date(Date.now() - 3000_000).toISOString(),
      status: "success",
    },
    failure_pattern: { consecutive_failures: 0, is_currently_failing: false },
    ticker_success_rate: 0.98,
  },
  meta: { total_count: 1, truncated: false, schema_version: "v1" },
};

test("renders pipeline selector with known pipelines", () => {
  mockUseAdminPipelines.mockReturnValue({
    data: MOCK_RESULT,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  const select = screen.getByLabelText("Select pipeline");
  expect(select).toBeInTheDocument();
  expect(select).toHaveValue("nightly_price_refresh");
});

test("renders loading skeletons when loading", () => {
  mockUseAdminPipelines.mockReturnValue({
    data: undefined,
    isLoading: true,
    error: null,
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("renders error state", () => {
  mockUseAdminPipelines.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: new Error("fail"),
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  expect(screen.getByText(/Failed to load pipeline data/)).toBeInTheDocument();
});

test("renders run rows with status and ticker counts", () => {
  mockUseAdminPipelines.mockReturnValue({
    data: MOCK_RESULT,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  expect(screen.getByText("success")).toBeInTheDocument();
  expect(screen.getByText("98/100")).toBeInTheDocument();
  expect(screen.getByText("200s")).toBeInTheDocument();
});

test("renders ticker success rate", () => {
  mockUseAdminPipelines.mockReturnValue({
    data: MOCK_RESULT,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  expect(screen.getByText(/98\.0%/)).toBeInTheDocument();
});

test("expands run detail on click", async () => {
  mockUseAdminPipelines.mockReturnValue({
    data: MOCK_RESULT,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  await userEvent.click(screen.getByText("success"));
  expect(screen.getByText(/fetch: 120s/)).toBeInTheDocument();
  expect(screen.getByText(/compute: 80s/)).toBeInTheDocument();
});

test("shows consecutive failures badge when failing", () => {
  const failingData = {
    ...MOCK_RESULT,
    result: {
      ...MOCK_RESULT.result,
      failure_pattern: { consecutive_failures: 3, is_currently_failing: true },
    },
  };
  mockUseAdminPipelines.mockReturnValue({
    data: failingData,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useAdminPipelines>);

  render(<PipelineHealth />, { wrapper });
  expect(screen.getByText("3 consecutive failures")).toBeInTheDocument();
});
