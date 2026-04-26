import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── Mock Recharts (ResponsiveContainer renders nothing in jsdom) ─────────────
jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div style={{ width: 100, height: 32 }}>{children}</div>
  ),
}));

// ── Mock hooks ──────────────────────────────────────────────────────────────
const mockUseMarketBriefing = jest.fn(() => ({ data: undefined, isLoading: false, isError: false }));
const mockUseRecommendations = jest.fn(() => ({ data: undefined, isLoading: false, isError: false }));
const mockUseBulkSignalsByTickers = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUsePortfolioSummary = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUsePortfolioHealth = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUsePortfolioHealthHistory = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUseUserDashboardNews = jest.fn(() => ({ data: undefined, isLoading: false }));

jest.mock("@/hooks/use-stocks", () => ({
  useMarketBriefing: () => mockUseMarketBriefing(),
  useRecommendations: () => mockUseRecommendations(),
  useBulkSignalsByTickers: () => mockUseBulkSignalsByTickers(),
  usePortfolioSummary: () => mockUsePortfolioSummary(),
  usePortfolioHealth: () => mockUsePortfolioHealth(),
  usePortfolioHealthHistory: () => mockUsePortfolioHealthHistory(),
  usePortfolioAnalytics: () => ({ data: undefined, isLoading: false }),
  useUserDashboardNews: () => mockUseUserDashboardNews(),
}));

const mockUseMacroSentiment = jest.fn(() => ({ data: undefined, isLoading: false }));

jest.mock("@/hooks/use-sentiment", () => ({
  useMacroSentiment: () => mockUseMacroSentiment(),
}));

jest.mock("@/hooks/use-convergence", () => ({
  usePortfolioConvergence: () => ({ data: undefined, isLoading: false }),
}));

jest.mock("@/hooks/use-forecasts", () => ({
  usePortfolioForecastFull: () => ({ data: undefined, isLoading: false }),
}));

const mockUseAlerts = jest.fn(() => ({ data: undefined, isLoading: false, isError: false }));

jest.mock("@/hooks/use-alerts", () => ({
  useAlerts: () => mockUseAlerts(),
}));

jest.mock("@/lib/market-hours", () => ({
  isMarketOpen: jest.fn(() => false),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/dashboard",
}));

jest.mock("@/contexts/chat-context", () => ({
  useChat: jest.fn(() => ({ chatOpen: false })),
}));

jest.mock("sonner", () => ({
  toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() },
}));

// ── Zone components ─────────────────────────────────────────────────────────

import { MarketPulseZone } from "@/app/(authenticated)/dashboard/_components/market-pulse-zone";
import { SignalsZone } from "@/app/(authenticated)/dashboard/_components/signals-zone";
import { PortfolioZone } from "@/app/(authenticated)/dashboard/_components/portfolio-zone";
import { AlertsZone } from "@/app/(authenticated)/dashboard/_components/alerts-zone";
import { NewsZone } from "@/app/(authenticated)/dashboard/_components/news-zone";

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

// ── MarketPulseZone ─────────────────────────────────────────────────────────

describe("MarketPulseZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Market Pulse heading", () => {
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("Market Pulse")).toBeInTheDocument();
  });

  it("shows market status badge", () => {
    renderWithQuery(<MarketPulseZone />);
    const badge = screen.getByText(/Market (Open|Closed)/);
    expect(badge).toBeInTheDocument();
  });

  it("shows loading skeletons when isLoading", () => {
    mockUseMarketBriefing.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderWithQuery(<MarketPulseZone />);
    const skeletons = container.querySelectorAll("[class*='animate-pulse']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error message when isError", () => {
    mockUseMarketBriefing.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("Unable to load market data.")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByLabelText("Market Pulse")).toBeInTheDocument();
  });

  it("renders bullish badge when macro_sentiment > 0.2", () => {
    mockUseMarketBriefing.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseMacroSentiment.mockReturnValue({
      data: { data: [{ macro_sentiment: 0.5, stock_sentiment: 0.3, sector_sentiment: 0.2, article_count: 5, confidence: 0.8, date: "2026-04-25", ticker: "MACRO", dominant_event_type: null, rationale_summary: null, quality_flag: "ok" }] },
      isLoading: false,
    } as never);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("▲ Bullish")).toBeInTheDocument();
  });

  it("renders bearish badge when macro_sentiment < -0.2", () => {
    mockUseMarketBriefing.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseMacroSentiment.mockReturnValue({
      data: { data: [{ macro_sentiment: -0.5, stock_sentiment: -0.3, sector_sentiment: -0.2, article_count: 5, confidence: 0.8, date: "2026-04-25", ticker: "MACRO", dominant_event_type: null, rationale_summary: null, quality_flag: "ok" }] },
      isLoading: false,
    } as never);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("▼ Bearish")).toBeInTheDocument();
  });

  it("renders neutral badge when macro_sentiment between -0.2 and 0.2", () => {
    mockUseMarketBriefing.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseMacroSentiment.mockReturnValue({
      data: { data: [{ macro_sentiment: 0.1, stock_sentiment: 0.1, sector_sentiment: 0.0, article_count: 5, confidence: 0.8, date: "2026-04-25", ticker: "MACRO", dominant_event_type: null, rationale_summary: null, quality_flag: "ok" }] },
      isLoading: false,
    } as never);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("— Neutral")).toBeInTheDocument();
  });

  it("does not render macro badge when sentiment data is empty array", () => {
    mockUseMarketBriefing.mockReturnValue({ data: undefined, isLoading: false, isError: false });
    mockUseMacroSentiment.mockReturnValue({
      data: { data: [] },
      isLoading: false,
    } as never);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.queryByText(/Bullish|Bearish|Neutral/)).not.toBeInTheDocument();
  });
});

// ── SignalsZone ─────────────────────────────────────────────────────────────

describe("SignalsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Your Signals heading", () => {
    renderWithQuery(<SignalsZone />);
    expect(screen.getByText("Your Signals")).toBeInTheDocument();
  });

  it("shows empty state when no recommendations", () => {
    mockUseRecommendations.mockReturnValue({ data: [], isLoading: false, isError: false } as never);
    renderWithQuery(<SignalsZone />);
    expect(screen.getByText("No signals yet")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUseRecommendations.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderWithQuery(<SignalsZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("has aria-label on sections", () => {
    mockUseRecommendations.mockReturnValue({ data: [], isLoading: false, isError: false } as never);
    renderWithQuery(<SignalsZone />);
    expect(screen.getByLabelText("Your Signals")).toBeInTheDocument();
    expect(screen.getByLabelText("Top Movers")).toBeInTheDocument();
  });
});

// ── PortfolioZone ───────────────────────────────────────────────────────────

describe("PortfolioZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Portfolio Overview heading", () => {
    renderWithQuery(<PortfolioZone />);
    expect(screen.getByText("Portfolio Overview")).toBeInTheDocument();
  });

  it("shows empty state when no portfolio", () => {
    mockUsePortfolioSummary.mockReturnValue({ data: { position_count: 0, total_value: 0, total_cost_basis: 0, unrealized_pnl: 0, unrealized_pnl_pct: 0, sectors: [] }, isLoading: false } as never);
    renderWithQuery(<PortfolioZone />);
    expect(screen.getByText("No portfolio yet")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUsePortfolioSummary.mockReturnValue({ data: undefined, isLoading: true });
    mockUsePortfolioHealth.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderWithQuery(<PortfolioZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("has aria-label on section", () => {
    renderWithQuery(<PortfolioZone />);
    expect(screen.getByLabelText("Portfolio Overview")).toBeInTheDocument();
  });

  it("renders health sparkline when history has >=2 data points", () => {
    mockUsePortfolioSummary.mockReturnValue({
      data: { position_count: 2, total_value: 10000, total_cost_basis: 9000, unrealized_pnl: 1000, unrealized_pnl_pct: 11.1, sectors: [], portfolio_id: "p1" },
      isLoading: false,
    } as never);
    mockUsePortfolioHealth.mockReturnValue({
      data: { grade: "A", health_score: 85, components: [], concerns: [], strengths: [] },
      isLoading: false,
    } as never);
    mockUsePortfolioHealthHistory.mockReturnValue({
      data: [
        { snapshot_date: "2026-04-24", health_score: 82, grade: "A", diversification_score: 0.8, signal_quality_score: 0.9, risk_score: 0.7, income_score: 0.5, sector_balance_score: 0.8, hhi: 0.1, weighted_beta: null, weighted_sharpe: null, weighted_yield: null, position_count: 2 },
        { snapshot_date: "2026-04-25", health_score: 85, grade: "A", diversification_score: 0.8, signal_quality_score: 0.9, risk_score: 0.7, income_score: 0.5, sector_balance_score: 0.8, hhi: 0.1, weighted_beta: null, weighted_sharpe: null, weighted_yield: null, position_count: 2 },
      ],
      isLoading: false,
    } as never);
    const { container } = renderWithQuery(<PortfolioZone />);
    // The sparkline wrapper div has a fixed height of h-8 (32px) — our ResponsiveContainer mock renders a div with height:32
    const sparklineWrapper = container.querySelector("div[style*='height: 32']");
    expect(sparklineWrapper).toBeInTheDocument();
  });

  it("does not render sparkline when history has <2 data points", () => {
    mockUsePortfolioSummary.mockReturnValue({
      data: { position_count: 2, total_value: 10000, total_cost_basis: 9000, unrealized_pnl: 1000, unrealized_pnl_pct: 11.1, sectors: [], portfolio_id: "p1" },
      isLoading: false,
    } as never);
    mockUsePortfolioHealth.mockReturnValue({
      data: { grade: "A", health_score: 85, components: [], concerns: [], strengths: [] },
      isLoading: false,
    } as never);
    mockUsePortfolioHealthHistory.mockReturnValue({
      data: [
        { snapshot_date: "2026-04-25", health_score: 85, grade: "A", diversification_score: 0.8, signal_quality_score: 0.9, risk_score: 0.7, income_score: 0.5, sector_balance_score: 0.8, hhi: 0.1, weighted_beta: null, weighted_sharpe: null, weighted_yield: null, position_count: 2 },
      ],
      isLoading: false,
    } as never);
    const { container } = renderWithQuery(<PortfolioZone />);
    // With only 1 data point, no sparkline wrapper should render
    const sparklineWrapper = container.querySelector("div[style*='height: 32']");
    expect(sparklineWrapper).not.toBeInTheDocument();
  });
});

// ── AlertsZone ──────────────────────────────────────────────────────────────

describe("AlertsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Alerts heading", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as never);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Alerts")).toBeInTheDocument();
  });

  it("shows empty state when no alerts", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as never);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("No alerts")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUseAlerts.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderWithQuery(<AlertsZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error message when isError", () => {
    mockUseAlerts.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Unable to load alerts.")).toBeInTheDocument();
  });

  it("renders alert items with severity styling", () => {
    mockUseAlerts.mockReturnValue({
      data: {
        alerts: [
          { id: "1", title: "Price Drop", message: "AAPL dropped 5%", severity: "warning", ticker: "AAPL", is_read: false, created_at: "2026-03-30T10:00:00Z", alert_type: "price", metadata: {} },
        ],
        total: 1,
        unreadCount: 1,
      },
      isLoading: false,
      isError: false,
    } as never);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Price Drop")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as never);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
  });
});

// ── SignalsZone with populated data ──────────────────────────────────────────

describe("SignalsZone — populated data", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders signal cards when recommendations and bulk signals exist", () => {
    mockUseRecommendations.mockReturnValue({
      data: [
        { ticker: "AAPL", action: "BUY", composite_score: 9.2, name: "Apple" },
      ],
      isLoading: false,
      isError: false,
    } as never);
    mockUseBulkSignalsByTickers.mockReturnValue({
      data: {
        items: [
          { ticker: "AAPL", name: "Apple Inc.", rsi_value: 42, rsi_signal: "neutral", macd_signal: "bullish_crossover", sharpe_ratio: 1.2, sma_signal: "above", composite_score: 9.2 },
        ],
      },
      isLoading: false,
    } as never);
    renderWithQuery(<SignalsZone />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
  });
});

// ── AlertsZone with populated data ──────────────────────────────────────────

describe("AlertsZone — populated data", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders alert content with severity and ticker", () => {
    mockUseAlerts.mockReturnValue({
      data: {
        alerts: [
          { id: "1", title: "Score dropped", message: "INTC score fell below threshold", severity: "critical", ticker: "INTC", is_read: false, created_at: "2026-03-30T10:00:00Z", alert_type: "signal", metadata: {} },
        ],
        total: 1,
        unreadCount: 1,
      },
      isLoading: false,
      isError: false,
    } as never);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Score dropped")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText("INTC")).toBeInTheDocument();
  });
});

// ── NewsZone with populated data ────────────────────────────────────────────

describe("NewsZone — populated data", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders article titles from dashboard news", () => {
    mockUseUserDashboardNews.mockReturnValue({
      data: {
        articles: [
          { title: "Apple earnings beat", link: "https://example.com", publisher: "Reuters", published: "1h ago", source: "news", portfolio_ticker: "AAPL" },
        ],
        ticker_count: 1,
      },
      isLoading: false,
    } as never);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText("Apple earnings beat")).toBeInTheDocument();
    expect(screen.getByText("Reuters")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });
});

// ── NewsZone ────────────────────────────────────────────────────────────────

describe("NewsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders News & Intelligence heading", () => {
    renderWithQuery(<NewsZone />);
    expect(screen.getByText(/News/)).toBeInTheDocument();
  });

  it("shows empty state when no articles", () => {
    mockUseUserDashboardNews.mockReturnValue({ data: { articles: [], ticker_count: 0 }, isLoading: false } as never);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText("No news yet")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUseUserDashboardNews.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderWithQuery(<NewsZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders articles when data available", () => {
    mockUseUserDashboardNews.mockReturnValue({
      data: {
        articles: [
          { title: "AAPL beats earnings", link: "https://example.com/1", publisher: "Reuters", published: "2h ago", source: "news", portfolio_ticker: "AAPL" },
          { title: "MSFT cloud growth", link: "https://example.com/2", publisher: "Bloomberg", published: "3h ago", source: "news", portfolio_ticker: "MSFT" },
        ],
        ticker_count: 2,
      },
      isLoading: false,
    } as never);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText("AAPL beats earnings")).toBeInTheDocument();
    expect(screen.getByText("MSFT cloud growth")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    renderWithQuery(<NewsZone />);
    expect(screen.getByLabelText("News and Intelligence")).toBeInTheDocument();
  });
});
