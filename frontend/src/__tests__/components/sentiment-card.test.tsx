import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SentimentCard } from "@/components/sentiment-card";

const mockSentiment = {
  data: {
    ticker: "AAPL",
    data: [
      {
        date: "2026-04-24",
        ticker: "AAPL",
        stock_sentiment: 0.35,
        sector_sentiment: 0.18,
        macro_sentiment: -0.11,
        article_count: 8,
        confidence: 0.82,
        dominant_event_type: "earnings",
      },
      {
        date: "2026-04-25",
        ticker: "AAPL",
        stock_sentiment: 0.42,
        sector_sentiment: 0.2,
        macro_sentiment: -0.08,
        article_count: 12,
        confidence: 0.85,
        dominant_event_type: "product",
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: jest.fn(),
};

const mockArticles = {
  data: {
    ticker: "AAPL",
    articles: [
      {
        headline: "Apple Reports Strong Q2 Earnings",
        source: "Reuters",
        source_url: "https://example.com/1",
        ticker: "AAPL",
        published_at: "2026-04-25T10:00:00Z",
        event_type: "earnings",
        scored_at: "2026-04-25T12:00:00Z",
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  },
  isLoading: false,
};

jest.mock("@/hooks/use-sentiment", () => ({
  useSentiment: () => mockSentiment,
  useTickerArticles: () => mockArticles,
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

describe("SentimentCard", () => {
  it("renders 3 sentiment tiles with values", () => {
    render(<SentimentCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText("+0.42")).toBeInTheDocument();
    expect(screen.getByText("+0.20")).toBeInTheDocument();
    // U+2212 MINUS SIGN
    expect(screen.getByText("\u22120.08")).toBeInTheDocument();
  });

  it("renders article count in collapsible header", () => {
    render(<SentimentCard ticker="AAPL" />, { wrapper });
    expect(screen.getByText("1")).toBeInTheDocument(); // article count
    expect(screen.getByText(/recent articles/i)).toBeInTheDocument();
  });

  it("returns null when no data", () => {
    const orig = mockSentiment.data;
    // @ts-expect-error — testing null data
    mockSentiment.data = undefined;
    const { container } = render(<SentimentCard ticker="AAPL" />, { wrapper });
    expect(container.firstChild).toBeNull();
    mockSentiment.data = orig;
  });
});
