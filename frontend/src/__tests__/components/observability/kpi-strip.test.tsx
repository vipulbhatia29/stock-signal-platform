import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KPIStrip } from "@/app/(authenticated)/observability/_components/kpi-strip";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

describe("KPIStrip", () => {
  it("renders 5 KPI tiles when data is loaded", () => {
    (obsHooks.useObservabilityKPIs as jest.Mock).mockReturnValue({
      data: {
        queries_today: 42,
        avg_latency_ms: 1200,
        avg_cost_per_query: 0.003,
        pass_rate: 0.87,
        fallback_rate_pct: 0.02,
      },
      isLoading: false,
    });
    wrap(<KPIStrip />);
    expect(screen.getAllByTestId("stat-tile")).toHaveLength(5);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders skeletons when loading", () => {
    (obsHooks.useObservabilityKPIs as jest.Mock).mockReturnValue({
      data: undefined,
      isLoading: true,
    });
    wrap(<KPIStrip />);
    const skeletons = document.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThanOrEqual(5);
  });

  it("handles null pass_rate", () => {
    (obsHooks.useObservabilityKPIs as jest.Mock).mockReturnValue({
      data: {
        queries_today: 0,
        avg_latency_ms: 0,
        avg_cost_per_query: 0,
        pass_rate: null,
        fallback_rate_pct: 0,
      },
      isLoading: false,
    });
    wrap(<KPIStrip />);
    // null pass_rate should render "—"
    const tiles = screen.getAllByTestId("stat-tile");
    expect(tiles.length).toBe(5);
  });
});
