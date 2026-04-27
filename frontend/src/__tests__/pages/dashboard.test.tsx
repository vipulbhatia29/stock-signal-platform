import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* eslint-disable @typescript-eslint/no-explicit-any */
const mockUseWatchlist = jest.fn((): any => ({ data: [], isLoading: false }));
const mockUsePositions = jest.fn((): any => ({ data: [], isLoading: false }));
const mockUseAddToWatchlist = jest.fn((): any => ({ mutate: jest.fn() }));

jest.mock("@/hooks/use-stocks", () => ({
  useWatchlist: () => mockUseWatchlist(),
  usePositions: () => mockUsePositions(),
  useAddToWatchlist: () => mockUseAddToWatchlist(),
  useMarketBriefing: () => ({ data: undefined, isLoading: false }),
}));

jest.mock("@/components/allocation-donut", () => ({
  AllocationDonut: () => <div data-testid="allocation-donut" />,
}));

jest.mock("@/components/motion-primitives", () => ({
  PageTransition: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

jest.mock("@/components/migration-toast", () => ({
  MigrationToast: () => null,
}));

jest.mock("@/components/welcome-banner", () => ({
  WelcomeBanner: (props: { onAddTicker: (t: string) => void }) => (
    <div data-testid="welcome-banner" onClick={() => props.onAddTicker("AAPL")}>
      Welcome
    </div>
  ),
}));

jest.mock(
  "@/app/(authenticated)/dashboard/_components/kpi-row",
  () => ({ KPIRow: () => <div data-testid="kpi-row" /> })
);
jest.mock(
  "@/app/(authenticated)/dashboard/_components/market-pulse-zone",
  () => ({ MarketPulseZone: () => <div data-testid="market-pulse" /> })
);
jest.mock(
  "@/app/(authenticated)/dashboard/_components/action-required-zone",
  () => ({ ActionRequiredZone: () => <div data-testid="action-required" /> })
);
jest.mock(
  "@/app/(authenticated)/dashboard/_components/top-movers-zone",
  () => ({ TopMoversZone: () => <div data-testid="top-movers" /> })
);
jest.mock(
  "@/app/(authenticated)/dashboard/_components/bulletin-zone",
  () => ({ BulletinZone: () => <div data-testid="bulletin" /> })
);
jest.mock(
  "@/app/(authenticated)/dashboard/_components/alerts-zone",
  () => ({ AlertsZone: () => <div data-testid="alerts" /> })
);
jest.mock(
  "@/app/(authenticated)/dashboard/_components/news-zone",
  () => ({ NewsZone: () => <div data-testid="news" /> })
);

import DashboardPage from "@/app/(authenticated)/dashboard/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client: qc }, children);
}

describe("DashboardPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders WelcomeBanner when watchlist and positions are empty", () => {
    mockUseWatchlist.mockReturnValue({ data: [], isLoading: false });
    mockUsePositions.mockReturnValue({ data: [], isLoading: false });

    render(<DashboardPage />, { wrapper });

    expect(screen.getByTestId("welcome-banner")).toBeInTheDocument();
  });

  it("hides WelcomeBanner when watchlist has items", () => {
    mockUseWatchlist.mockReturnValue({
      data: [{ ticker: "AAPL" }],
      isLoading: false,
    });
    mockUsePositions.mockReturnValue({ data: [], isLoading: false });

    render(<DashboardPage />, { wrapper });

    expect(screen.queryByTestId("welcome-banner")).not.toBeInTheDocument();
  });

  it("hides WelcomeBanner when positions exist", () => {
    mockUseWatchlist.mockReturnValue({ data: [], isLoading: false });
    mockUsePositions.mockReturnValue({
      data: [{ ticker: "MSFT" }],
      isLoading: false,
    });

    render(<DashboardPage />, { wrapper });

    expect(screen.queryByTestId("welcome-banner")).not.toBeInTheDocument();
  });
});
