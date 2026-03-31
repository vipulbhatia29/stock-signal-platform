import { render, screen } from "@testing-library/react";
import { QueryRowDetail } from "@/app/(authenticated)/observability/_components/query-row-detail";
import { useQueryDetail } from "@/hooks/use-observability";

jest.mock("@/hooks/use-observability", () => ({
  useQueryDetail: jest.fn(),
}));

const mockDetail = {
  query_id: "q1",
  query_text: "Analyze AAPL fundamentals and forecast",
  steps: [
    { step_number: 1, action: "llm.groq.llama-3.3-70b", type_tag: "llm" as const, model_name: "llama-3.3-70b", input_summary: "\u2192 groq/llama-3.3-70b", output_summary: "256 tokens, 1200ms, $0.0012", latency_ms: 1200, cost_usd: 0.0012, cache_hit: false },
    { step_number: 2, action: "tool.get_stock_data", type_tag: "db" as const, model_name: null, input_summary: '{"ticker": "AAPL"}', output_summary: "1 row, 45 fields", latency_ms: 50, cost_usd: null, cache_hit: true },
    { step_number: 3, action: "tool.web_search", type_tag: "external" as const, model_name: null, input_summary: '{"query": "AAPL news"}', output_summary: "3 results", latency_ms: 800, cost_usd: null, cache_hit: false },
  ],
  langfuse_trace_url: "https://langfuse.example.com/trace/abc",
};

const mockedUseQueryDetail = useQueryDetail as jest.MockedFunction<typeof useQueryDetail>;

function mockHookReturn(overrides: Partial<ReturnType<typeof useQueryDetail>>) {
  mockedUseQueryDetail.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof useQueryDetail>);
}

describe("QueryRowDetail", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders all steps", () => {
    mockHookReturn({ data: mockDetail });
    render(<QueryRowDetail queryId="q1" queryText="Analyze AAPL" />);
    expect(screen.getByText("llm.groq.llama-3.3-70b")).toBeInTheDocument();
    expect(screen.getByText("tool.get_stock_data")).toBeInTheDocument();
    expect(screen.getByText("tool.web_search")).toBeInTheDocument();
  });

  it("shows type tag pills", () => {
    mockHookReturn({ data: mockDetail });
    render(<QueryRowDetail queryId="q1" queryText="Analyze AAPL" />);
    expect(screen.getByText("llm")).toBeInTheDocument();
    expect(screen.getByText("db")).toBeInTheDocument();
    expect(screen.getByText("external")).toBeInTheDocument();
  });

  it("shows cached badge", () => {
    mockHookReturn({ data: mockDetail });
    render(<QueryRowDetail queryId="q1" queryText="Analyze AAPL" />);
    expect(screen.getByText("cached")).toBeInTheDocument();
  });

  it("shows Langfuse link when URL present", () => {
    mockHookReturn({ data: mockDetail });
    render(<QueryRowDetail queryId="q1" queryText="Analyze AAPL" />);
    const link = screen.getByText("View in Langfuse");
    expect(link).toHaveAttribute("href", mockDetail.langfuse_trace_url);
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("hides Langfuse link when URL is null", () => {
    const noTrace = { ...mockDetail, langfuse_trace_url: null };
    mockHookReturn({ data: noTrace });
    render(<QueryRowDetail queryId="q1" queryText="test" />);
    expect(screen.queryByText("View in Langfuse")).not.toBeInTheDocument();
  });

  it("shows loading skeleton", () => {
    mockHookReturn({ isLoading: true });
    render(<QueryRowDetail queryId="q1" queryText="test" />);
    const skeletons = document.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error state", () => {
    mockHookReturn({ isError: true });
    render(<QueryRowDetail queryId="q1" queryText="test" />);
    expect(screen.getByText("Failed to load query details. Please try again.")).toBeInTheDocument();
  });
});
