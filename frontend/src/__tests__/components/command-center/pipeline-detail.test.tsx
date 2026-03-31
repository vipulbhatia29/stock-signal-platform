import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { PipelineDetail } from "@/components/command-center/pipeline-detail";
import type { PipelineRunEntry } from "@/types/command-center-drilldown";

const mockRuns: PipelineRunEntry[] = [
  {
    id: "run-1",
    pipeline_name: "nightly_ingest",
    started_at: "2026-03-31T02:00:00Z",
    completed_at: "2026-03-31T02:15:30Z",
    status: "success",
    total_duration_seconds: 930,
    tickers_succeeded: 48,
    tickers_failed: 2,
    tickers_total: 50,
    error_summary: { AAPL: "Timeout fetching fundamentals" },
    step_durations: { fetch_prices: 120, compute_signals: 450, store: 360 },
  },
  {
    id: "run-2",
    pipeline_name: "nightly_ingest",
    started_at: "2026-03-30T02:00:00Z",
    completed_at: null,
    status: "failed",
    total_duration_seconds: null,
    tickers_succeeded: 0,
    tickers_failed: 50,
    tickers_total: 50,
    error_summary: null,
    step_durations: null,
  },
];

describe("PipelineDetail", () => {
  it("renders run history table with rows", () => {
    render(<PipelineDetail data={{ runs: mockRuns, total: 2, days: 7 }} />);
    const table = screen.getByTestId("pipeline-table");
    expect(table).toBeInTheDocument();
    const rows = screen.getAllByTestId("pipeline-row");
    expect(rows).toHaveLength(2);
  });

  it("shows total and days summary", () => {
    render(<PipelineDetail data={{ runs: mockRuns, total: 2, days: 7 }} />);
    expect(screen.getByText("2 runs over last 7 days")).toBeInTheDocument();
  });

  it("displays status text", () => {
    render(<PipelineDetail data={{ runs: mockRuns, total: 2, days: 7 }} />);
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("formats duration correctly", () => {
    render(<PipelineDetail data={{ runs: mockRuns, total: 2, days: 7 }} />);
    // 930 seconds = 15m 30s
    expect(screen.getByText("15m 30s")).toBeInTheDocument();
  });

  it("expands row to show step durations and errors on click", async () => {
    const user = userEvent.setup();
    render(<PipelineDetail data={{ runs: mockRuns, total: 2, days: 7 }} />);

    // Click first row (has detail)
    const rows = screen.getAllByTestId("pipeline-row");
    await user.click(rows[0]);

    const detail = screen.getByTestId("pipeline-row-detail");
    expect(detail).toBeInTheDocument();
    expect(screen.getByText("Step Durations")).toBeInTheDocument();
    expect(screen.getByText("fetch_prices")).toBeInTheDocument();
    expect(screen.getByText("Timeout fetching fundamentals")).toBeInTheDocument();
  });

  it("collapses row on second click", async () => {
    const user = userEvent.setup();
    render(<PipelineDetail data={{ runs: mockRuns, total: 2, days: 7 }} />);

    const rows = screen.getAllByTestId("pipeline-row");
    await user.click(rows[0]);
    expect(screen.getByTestId("pipeline-row-detail")).toBeInTheDocument();

    await user.click(rows[0]);
    expect(screen.queryByTestId("pipeline-row-detail")).not.toBeInTheDocument();
  });

  it("shows empty state when no runs", () => {
    render(<PipelineDetail data={{ runs: [], total: 0, days: 7 }} />);
    expect(screen.getByText("No pipeline runs")).toBeInTheDocument();
  });
});
