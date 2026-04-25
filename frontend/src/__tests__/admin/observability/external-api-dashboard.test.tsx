import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExternalApiDashboard } from "@/app/(authenticated)/admin/observability/_components/external-api-dashboard";
import * as adminHooks from "@/hooks/use-admin-observability";
import type { AdminExternalsEnvelope } from "@/types/admin-observability";

jest.mock("@/hooks/use-admin-observability");
jest.mock("lucide-react", () => ({
  ChevronDown: () => <span data-testid="chevron-down" />,
  ChevronRight: () => <span data-testid="chevron-right" />,
}));

const MOCK_ENVELOPE: AdminExternalsEnvelope = {
  tool: "get_external_api_stats",
  window: { from: "2026-04-24T00:00:00Z", to: "2026-04-24T01:00:00Z" },
  result: {
    provider: "openai",
    window_min: 60,
    stats: {
      call_count: 120,
      success_count: 118,
      error_count: 2,
      success_rate: 0.983,
      p50_latency_ms: 450,
      p95_latency_ms: 1200,
      total_cost_usd: 0.0456,
    },
    error_breakdown: [
      { error_reason: "rate_limit", count: 1 },
      { error_reason: "timeout", count: 1 },
    ],
    rate_limit_events: 3,
  },
  meta: { total_count: 1, truncated: false, schema_version: "1.0" },
};

const LOADING_RESULT = { data: undefined, isLoading: true, error: null };
const ERROR_RESULT = { data: undefined, isLoading: false, error: new Error("Network error") };
const SUCCESS_RESULT = { data: MOCK_ENVELOPE, isLoading: false, error: null };

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(QueryClientProvider, { client: qc }, ui)
  );
}

beforeEach(() => {
  (adminHooks.useAdminExternals as jest.Mock).mockReturnValue(SUCCESS_RESULT);
});

describe("ExternalApiDashboard", () => {
  it("renders the section heading", () => {
    wrap(<ExternalApiDashboard />);
    expect(screen.getByText("External APIs")).toBeInTheDocument();
  });

  it("renders time window buttons", () => {
    wrap(<ExternalApiDashboard />);
    expect(screen.getByText("1h")).toBeInTheDocument();
    expect(screen.getByText("4h")).toBeInTheDocument();
    expect(screen.getByText("24h")).toBeInTheDocument();
  });

  it("renders column headers", () => {
    wrap(<ExternalApiDashboard />);
    expect(screen.getByText("Provider")).toBeInTheDocument();
    expect(screen.getByText("Calls")).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
    expect(screen.getByText("p95 Latency")).toBeInTheDocument();
    expect(screen.getByText("Cost")).toBeInTheDocument();
    expect(screen.getByText("Rate Limit")).toBeInTheDocument();
  });

  it("renders skeleton for loading providers", () => {
    (adminHooks.useAdminExternals as jest.Mock).mockReturnValue(LOADING_RESULT);
    const { container } = wrap(<ExternalApiDashboard />);
    const skeletons = container.querySelectorAll("[data-slot='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders error card when provider fetch fails", () => {
    (adminHooks.useAdminExternals as jest.Mock).mockReturnValue(ERROR_RESULT);
    wrap(<ExternalApiDashboard />);
    const errors = screen.getAllByText(/Failed to load .* stats/);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("renders call count for a provider", () => {
    wrap(<ExternalApiDashboard />);
    // 120 calls formatted with toLocaleString
    const callCells = screen.getAllByText(/120 calls/);
    expect(callCells.length).toBeGreaterThan(0);
  });

  it("renders success rate in green when >= 99%", () => {
    const highSuccess = {
      ...SUCCESS_RESULT,
      data: {
        ...MOCK_ENVELOPE,
        result: { ...MOCK_ENVELOPE.result, stats: { ...MOCK_ENVELOPE.result.stats, success_rate: 0.995 } },
      },
    };
    (adminHooks.useAdminExternals as jest.Mock).mockReturnValue(highSuccess);
    wrap(<ExternalApiDashboard />);
    const rateEl = screen.getAllByText(/99\.5%/)[0];
    expect(rateEl.className).toContain("text-emerald-400");
  });

  it("expands provider row on click to show error breakdown", async () => {
    wrap(<ExternalApiDashboard />);
    const buttons = screen.getAllByRole("button", { name: /openai/i });
    await userEvent.click(buttons[0]);
    expect(screen.getAllByText("Recent Errors").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/rate_limit/).length).toBeGreaterThan(0);
  });

  it("shows 'No errors in window' when error_breakdown is empty", async () => {
    const noErrors = {
      ...SUCCESS_RESULT,
      data: {
        ...MOCK_ENVELOPE,
        result: { ...MOCK_ENVELOPE.result, error_breakdown: [] },
      },
    };
    (adminHooks.useAdminExternals as jest.Mock).mockReturnValue(noErrors);
    wrap(<ExternalApiDashboard />);
    const buttons = screen.getAllByRole("button", { name: /openai/i });
    await userEvent.click(buttons[0]);
    expect(screen.getAllByText("No errors in window.").length).toBeGreaterThan(0);
  });

  it("highlights rate limit count in yellow when > 0", () => {
    wrap(<ExternalApiDashboard />);
    const rlCells = screen.getAllByText("3 RL");
    expect(rlCells[0].className).toContain("text-yellow-400");
  });
});
