import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── Mock hooks ──────────────────────────────────────────────────────────────

/* eslint-disable @typescript-eslint/no-explicit-any */
const mockUseMarketBriefing = jest.fn(() => ({ data: undefined, isLoading: false, isError: false }));
const mockUseRecommendations = jest.fn(() => ({ data: undefined, isLoading: false, isError: false }));
const mockUseBulkSignalsByTickers = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUsePortfolioSummary = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUsePortfolioHealth = jest.fn(() => ({ data: undefined, isLoading: false }));
const mockUseUserDashboardNews = jest.fn(() => ({ data: undefined, isLoading: false }));

jest.mock("@/hooks/use-stocks", () => ({
  useMarketBriefing: () => mockUseMarketBriefing(),
  useRecommendations: () => mockUseRecommendations(),
  useBulkSignalsByTickers: () => mockUseBulkSignalsByTickers(),
  usePortfolioSummary: () => mockUsePortfolioSummary(),
  usePortfolioHealth: () => mockUsePortfolioHealth(),
  useUserDashboardNews: () => mockUseUserDashboardNews(),
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
/* eslint-enable @typescript-eslint/no-explicit-any */

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
});

// ── SignalsZone ─────────────────────────────────────────────────────────────

describe("SignalsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Your Signals heading", () => {
    renderWithQuery(<SignalsZone />);
    expect(screen.getByText("Your Signals")).toBeInTheDocument();
  });

  it("shows empty state when no recommendations", () => {
    mockUseRecommendations.mockReturnValue({ data: [], isLoading: false, isError: false } as any);
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
    mockUseRecommendations.mockReturnValue({ data: [], isLoading: false, isError: false } as any);
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
    mockUsePortfolioSummary.mockReturnValue({ data: { position_count: 0, total_value: 0, total_cost_basis: 0, unrealized_pnl: 0, unrealized_pnl_pct: 0, sectors: [] }, isLoading: false } as any);
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
});

// ── AlertsZone ──────────────────────────────────────────────────────────────

describe("AlertsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Alerts heading", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as any);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Alerts")).toBeInTheDocument();
  });

  it("shows empty state when no alerts", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as any);
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
    } as any);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Price Drop")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as any);
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
    } as any);
    mockUseBulkSignalsByTickers.mockReturnValue({
      data: {
        items: [
          { ticker: "AAPL", name: "Apple Inc.", rsi_value: 42, rsi_signal: "neutral", macd_signal: "bullish_crossover", sharpe_ratio: 1.2, sma_signal: "above", composite_score: 9.2 },
        ],
      },
      isLoading: false,
    } as any);
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
    } as any);
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
    } as any);
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
    mockUseUserDashboardNews.mockReturnValue({ data: { articles: [], ticker_count: 0 }, isLoading: false } as any);
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
    } as any);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText("AAPL beats earnings")).toBeInTheDocument();
    expect(screen.getByText("MSFT cloud growth")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    renderWithQuery(<NewsZone />);
    expect(screen.getByLabelText("News and Intelligence")).toBeInTheDocument();
  });
});
