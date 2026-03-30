import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── Mock hooks ──────────────────────────────────────────────────────────────

jest.mock("@/hooks/use-stocks", () => ({
  useIndexes: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useRecommendations: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  usePositions: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  usePortfolioSummary: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useTrendingStocks: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useWatchlist: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useAddToWatchlist: jest.fn(() => ({ mutate: jest.fn() })),
}));

jest.mock("@/hooks/use-alerts", () => ({
  useAlerts: jest.fn(() => ({ data: undefined, isLoading: false, isError: false })),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/dashboard",
}));

jest.mock("next/link", () => {
  return function MockLink({ children, href, ...rest }: { children: React.ReactNode; href: string; [k: string]: unknown }) {
    return <a href={href} {...rest}>{children}</a>;
  };
});

jest.mock("@/contexts/chat-context", () => ({
  useChat: jest.fn(() => ({ chatOpen: false })),
}));

jest.mock("sonner", () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}));

jest.mock("@/lib/api", () => ({
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
}));

// Import hooks after mocking
import { useIndexes, useRecommendations, usePositions, usePortfolioSummary, useTrendingStocks, useWatchlist } from "@/hooks/use-stocks";
import { useAlerts } from "@/hooks/use-alerts";

const mockUseIndexes = useIndexes as jest.MockedFunction<typeof useIndexes>;
const mockUseRecommendations = useRecommendations as jest.MockedFunction<typeof useRecommendations>;
const mockUsePositions = usePositions as jest.MockedFunction<typeof usePositions>;
const mockUsePortfolioSummary = usePortfolioSummary as jest.MockedFunction<typeof usePortfolioSummary>;
const mockUseTrendingStocks = useTrendingStocks as jest.MockedFunction<typeof useTrendingStocks>;
const mockUseWatchlist = useWatchlist as jest.MockedFunction<typeof useWatchlist>;
const mockUseAlerts = useAlerts as jest.MockedFunction<typeof useAlerts>;

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
    mockUseIndexes.mockReturnValue({ data: [], isLoading: false, isError: false } as unknown as ReturnType<typeof useIndexes>);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("Market Pulse")).toBeInTheDocument();
  });

  it("shows market status badge", () => {
    mockUseIndexes.mockReturnValue({ data: [], isLoading: false, isError: false } as unknown as ReturnType<typeof useIndexes>);
    renderWithQuery(<MarketPulseZone />);
    // Should show either Market Open or Market Closed
    const badge = screen.getByText(/Market (Open|Closed)/);
    expect(badge).toBeInTheDocument();
  });

  it("shows loading skeletons when isLoading", () => {
    mockUseIndexes.mockReturnValue({ data: undefined, isLoading: true, isError: false } as unknown as ReturnType<typeof useIndexes>);
    const { container } = renderWithQuery(<MarketPulseZone />);
    // Skeleton elements have animate-pulse class
    const skeletons = container.querySelectorAll("[class*='animate-pulse']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error message when isError", () => {
    mockUseIndexes.mockReturnValue({ data: undefined, isLoading: false, isError: true } as unknown as ReturnType<typeof useIndexes>);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("Unable to load market data.")).toBeInTheDocument();
  });

  it("shows empty message when no indexes", () => {
    mockUseIndexes.mockReturnValue({ data: [], isLoading: false, isError: false } as unknown as ReturnType<typeof useIndexes>);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByText("No index data available yet.")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    mockUseIndexes.mockReturnValue({ data: [], isLoading: false, isError: false } as unknown as ReturnType<typeof useIndexes>);
    renderWithQuery(<MarketPulseZone />);
    expect(screen.getByLabelText("Market Pulse")).toBeInTheDocument();
  });
});

// ── SignalsZone ─────────────────────────────────────────────────────────────

describe("SignalsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Your Signals heading", () => {
    mockUseRecommendations.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof useRecommendations>);
    mockUsePositions.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof usePositions>);
    mockUseTrendingStocks.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof useTrendingStocks>);
    renderWithQuery(<SignalsZone />);
    expect(screen.getByText("Your Signals")).toBeInTheDocument();
  });

  it("shows empty state when no recommendations", () => {
    mockUseRecommendations.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof useRecommendations>);
    mockUsePositions.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof usePositions>);
    mockUseTrendingStocks.mockReturnValue({ data: { items: [] }, isLoading: false } as unknown as ReturnType<typeof useTrendingStocks>);
    renderWithQuery(<SignalsZone />);
    expect(screen.getByText("No signals yet")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUseRecommendations.mockReturnValue({ data: undefined, isLoading: true } as unknown as ReturnType<typeof useRecommendations>);
    mockUsePositions.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof usePositions>);
    mockUseTrendingStocks.mockReturnValue({ data: undefined, isLoading: true } as unknown as ReturnType<typeof useTrendingStocks>);
    const { container } = renderWithQuery(<SignalsZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("has aria-label on sections", () => {
    mockUseRecommendations.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof useRecommendations>);
    mockUsePositions.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof usePositions>);
    mockUseTrendingStocks.mockReturnValue({ data: { items: [] }, isLoading: false } as unknown as ReturnType<typeof useTrendingStocks>);
    renderWithQuery(<SignalsZone />);
    expect(screen.getByLabelText("Your Signals")).toBeInTheDocument();
    expect(screen.getByLabelText("Top Movers")).toBeInTheDocument();
  });
});

// ── PortfolioZone ───────────────────────────────────────────────────────────

describe("PortfolioZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Portfolio Overview heading", () => {
    mockUsePortfolioSummary.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof usePortfolioSummary>);
    mockUsePositions.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof usePositions>);
    renderWithQuery(<PortfolioZone />);
    expect(screen.getByText("Portfolio Overview")).toBeInTheDocument();
  });

  it("shows empty state when no positions", () => {
    mockUsePortfolioSummary.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof usePortfolioSummary>);
    mockUsePositions.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof usePositions>);
    renderWithQuery(<PortfolioZone />);
    expect(screen.getByText("No portfolio yet")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUsePortfolioSummary.mockReturnValue({ data: undefined, isLoading: true } as unknown as ReturnType<typeof usePortfolioSummary>);
    mockUsePositions.mockReturnValue({ data: undefined, isLoading: true } as unknown as ReturnType<typeof usePositions>);
    const { container } = renderWithQuery(<PortfolioZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("has aria-label on section", () => {
    mockUsePortfolioSummary.mockReturnValue({ data: undefined, isLoading: false } as unknown as ReturnType<typeof usePortfolioSummary>);
    mockUsePositions.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof usePositions>);
    renderWithQuery(<PortfolioZone />);
    expect(screen.getByLabelText("Portfolio Overview")).toBeInTheDocument();
  });
});

// ── AlertsZone ──────────────────────────────────────────────────────────────

describe("AlertsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Alerts heading", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as unknown as ReturnType<typeof useAlerts>);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Alerts")).toBeInTheDocument();
  });

  it("shows empty state when no alerts", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as unknown as ReturnType<typeof useAlerts>);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("No alerts")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUseAlerts.mockReturnValue({ data: undefined, isLoading: true, isError: false } as unknown as ReturnType<typeof useAlerts>);
    const { container } = renderWithQuery(<AlertsZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("shows error message when isError", () => {
    mockUseAlerts.mockReturnValue({ data: undefined, isLoading: false, isError: true } as unknown as ReturnType<typeof useAlerts>);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Unable to load alerts.")).toBeInTheDocument();
  });

  it("renders alert items with severity styling", () => {
    mockUseAlerts.mockReturnValue({
      data: {
        alerts: [
          { id: "1", title: "Price Drop", message: "AAPL dropped 5%", severity: "warning", ticker: "AAPL", is_read: false, created_at: "2026-03-30T10:00:00Z" },
        ],
        total: 1,
        unreadCount: 1,
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useAlerts>);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByText("Price Drop")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    mockUseAlerts.mockReturnValue({ data: { alerts: [], total: 0, unreadCount: 0 }, isLoading: false, isError: false } as unknown as ReturnType<typeof useAlerts>);
    renderWithQuery(<AlertsZone />);
    expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
  });
});

// ── NewsZone ────────────────────────────────────────────────────────────────

describe("NewsZone", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders News & Intelligence heading", () => {
    mockUseWatchlist.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof useWatchlist>);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText(/News/)).toBeInTheDocument();
  });

  it("shows empty state when no watchlist data", () => {
    mockUseWatchlist.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof useWatchlist>);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText("No news yet")).toBeInTheDocument();
  });

  it("shows loading skeletons when loading", () => {
    mockUseWatchlist.mockReturnValue({ data: undefined, isLoading: true } as unknown as ReturnType<typeof useWatchlist>);
    const { container } = renderWithQuery(<NewsZone />);
    const skeletons = container.querySelectorAll("[class*='bg-card2']");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders ticker links when watchlist has data", () => {
    mockUseWatchlist.mockReturnValue({
      data: [
        { ticker: "AAPL", name: "Apple Inc" },
        { ticker: "MSFT", name: "Microsoft" },
      ],
      isLoading: false,
    } as unknown as ReturnType<typeof useWatchlist>);
    renderWithQuery(<NewsZone />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("has aria-label on section", () => {
    mockUseWatchlist.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<typeof useWatchlist>);
    renderWithQuery(<NewsZone />);
    expect(screen.getByLabelText("News and Intelligence")).toBeInTheDocument();
  });
});
