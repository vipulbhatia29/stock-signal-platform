import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* eslint-disable @typescript-eslint/no-explicit-any */
const mockUseBulkSignals = jest.fn((): any => ({ data: undefined, isLoading: false }));
const mockUseWatchlist = jest.fn((): any => ({ data: undefined, isLoading: false }));
const mockUseIndexes = jest.fn((): any => ({ data: [], isLoading: false }));

jest.mock("@/hooks/use-stocks", () => ({
  useBulkSignals: () => mockUseBulkSignals(),
  useWatchlist: () => mockUseWatchlist(),
  useIndexes: () => mockUseIndexes(),
}));

let mockSearchParams = new URLSearchParams();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useSearchParams: () => mockSearchParams,
  usePathname: () => "/screener",
}));

jest.mock("@/lib/density-context", () => ({
  DensityProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useDensity: () => ({ density: "comfortable" as const, toggleDensity: jest.fn() }),
}));

jest.mock("@/components/screener-filters", () => ({
  ScreenerFilters: () => <div data-testid="screener-filters" />,
}));

jest.mock("@/components/screener-table", () => ({
  ScreenerTable: () => <div data-testid="screener-table" />,
}));

jest.mock("@/components/screener-grid", () => ({
  ScreenerGrid: () => <div data-testid="screener-grid" />,
}));

jest.mock("@/components/pagination-controls", () => ({
  PaginationControls: () => <div data-testid="pagination" />,
}));

jest.mock("@/components/empty-state", () => ({
  EmptyState: ({ title, description }: { title: string; description: string }) => (
    <div data-testid="empty-state">
      <span>{title}</span>
      <span>{description}</span>
    </div>
  ),
}));

jest.mock("@/components/motion-primitives", () => ({
  PageTransition: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));
/* eslint-enable @typescript-eslint/no-explicit-any */

import ScreenerPage from "@/app/(authenticated)/screener/page";

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ScreenerPage — Watchlist tab", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSearchParams = new URLSearchParams();
  });

  it("renders All Stocks and Watchlist tabs", () => {
    renderWithQuery(<ScreenerPage />);
    expect(screen.getByText("All Stocks")).toBeInTheDocument();
    expect(screen.getByText(/Watchlist/)).toBeInTheDocument();
  });

  it("shows badge count on watchlist tab when items exist", () => {
    mockUseWatchlist.mockReturnValue({
      data: [
        { ticker: "AAPL", added_at: "2026-01-01" },
        { ticker: "MSFT", added_at: "2026-01-01" },
      ],
      isLoading: false,
    });
    renderWithQuery(<ScreenerPage />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("with ?tab=watchlist param, watchlist tab is active", () => {
    mockSearchParams = new URLSearchParams("tab=watchlist");
    mockUseBulkSignals.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });
    renderWithQuery(<ScreenerPage />);
    // Watchlist button should have the active style class
    const watchlistBtn = screen.getByText(/Watchlist/);
    const parent = watchlistBtn.closest("button");
    expect(parent?.className).toContain("text-primary");
  });

  it("empty watchlist shows appropriate message", () => {
    mockSearchParams = new URLSearchParams("tab=watchlist");
    mockUseWatchlist.mockReturnValue({ data: [], isLoading: false });
    mockUseBulkSignals.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false });
    renderWithQuery(<ScreenerPage />);
    expect(screen.getByText("No watchlisted stocks")).toBeInTheDocument();
  });
});
