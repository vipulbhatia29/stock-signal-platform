import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueryTable } from "@/app/(authenticated)/observability/_components/query-table";
import * as obsHooks from "@/hooks/use-observability";
import React from "react";

jest.mock("@/hooks/use-observability");
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: jest.fn() }),
  usePathname: () => "/observability",
}));

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

const mockRow = {
  query_id: "q1",
  timestamp: "2026-03-31T10:00:00Z",
  query_text: "Analyze AAPL stock performance",
  agent_type: "react_v2",
  tools_used: ["get_stock_data", "analyze_stock", "get_fundamentals", "web_search"],
  llm_calls: 3,
  llm_models: ["llama-3.3-70b"],
  db_calls: 2,
  external_calls: 1,
  external_sources: ["web_search"],
  total_cost_usd: 0.0045,
  duration_ms: 3200,
  score: null,
  status: "completed",
};

describe("QueryTable", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (obsHooks.useObservabilityQueries as jest.Mock).mockReturnValue({
      data: { items: [mockRow], total: 1, page: 1, size: 25 },
      isLoading: false,
    });
    (obsHooks.useQueryDetail as jest.Mock).mockReturnValue({
      data: undefined,
      isLoading: false,
    });
  });

  it("renders table with query rows", () => {
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.getByText(/Analyze AAPL/)).toBeInTheDocument();
  });

  it("shows status badge", () => {
    wrap(<QueryTable isAdmin={false} />);
    const badges = screen.getAllByText("completed");
    // One in filter pills, one in the row status badge
    expect(badges.length).toBe(2);
    // The row badge should have the gain color class
    const rowBadge = badges.find((el) => el.className.includes("text-gain"));
    expect(rowBadge).toBeDefined();
  });

  it("caps tool badges at 3 with overflow", () => {
    wrap(<QueryTable isAdmin={false} />);
    // 4 tools, cap at 3, so "+1" overflow badge
    expect(screen.getByText("+1")).toBeInTheDocument();
  });

  it("shows empty state when no queries", () => {
    (obsHooks.useObservabilityQueries as jest.Mock).mockReturnValue({
      data: { items: [], total: 0, page: 1, size: 25 },
      isLoading: false,
    });
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.getByText(/No queries yet/)).toBeInTheDocument();
  });

  it("hides score column for non-admin", () => {
    wrap(<QueryTable isAdmin={false} />);
    expect(screen.queryByText("Score")).not.toBeInTheDocument();
  });

  it("shows score column for admin", () => {
    wrap(<QueryTable isAdmin={true} />);
    expect(screen.getByText("Score")).toBeInTheDocument();
  });
});
