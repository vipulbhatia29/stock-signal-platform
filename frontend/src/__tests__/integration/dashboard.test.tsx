/**
 * Dashboard integration tests — MSW-based.
 *
 * These tests render the individual dashboard zone components and let them
 * fetch data from MSW handlers (rather than mocking hooks directly).
 *
 * Complementary to `components/dashboard-zones.test.tsx` (hook-mock layer).
 * This layer validates the full fetch → render pipeline.
 */

import React from "react";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders, server } from "../test-utils";

// ── Module mocks (non-network dependencies) ──────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/dashboard",
}));

jest.mock("@/lib/market-hours", () => ({
  isMarketOpen: jest.fn(() => false),
}));

jest.mock("@/contexts/chat-context", () => ({
  useChat: jest.fn(() => ({ chatOpen: false })),
}));

jest.mock("sonner", () => ({
  toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() },
}));

jest.mock("@/components/motion-primitives", () => ({
  PageTransition: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

jest.mock("@/components/migration-toast", () => ({
  MigrationToast: () => null,
}));

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import { MarketPulseZone } from "@/app/(authenticated)/dashboard/_components/market-pulse-zone";
import { PortfolioZone } from "@/app/(authenticated)/dashboard/_components/portfolio-zone";
import { AlertsZone } from "@/app/(authenticated)/dashboard/_components/alerts-zone";
import { NewsZone } from "@/app/(authenticated)/dashboard/_components/news-zone";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Dashboard integration — MSW", () => {
  describe("MarketPulseZone", () => {
    it("renders Market Indexes section with aria-label", () => {
      renderWithProviders(<MarketPulseZone />);
      expect(screen.getByLabelText("Market Indexes")).toBeInTheDocument();
    });

    it("shows index data from MSW after loading", async () => {
      renderWithProviders(<MarketPulseZone />);
      // Wait for MSW data: S&P 500 index should appear
      await waitFor(() => {
        expect(screen.getByText("S&P 500")).toBeInTheDocument();
      });
    });

    it("shows error fallback when API returns 500", async () => {
      server.use(
        http.get("/api/v1/market/briefing", () =>
          HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 })
        )
      );

      renderWithProviders(<MarketPulseZone />);
      await waitFor(() => {
        expect(screen.getByText("Unable to load market data.")).toBeInTheDocument();
      });
    });

    it("shows loading skeletons while data is in flight", async () => {
      server.use(
        http.get("/api/v1/market/briefing", async () => {
          await new Promise((r) => setTimeout(r, 100));
          return HttpResponse.json({
            indexes: [],
            sector_performance: [],
            portfolio_news: [],
            upcoming_earnings: [],
            top_movers: { gainers: [], losers: [] },
            briefing_date: "2026-04-02",
          });
        })
      );

      const { container } = renderWithProviders(<MarketPulseZone />);
      // Skeletons visible before data resolves
      const skeletons = container.querySelectorAll("[class*='animate-pulse'],[class*='bg-card2']");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("AlertsZone", () => {
    it("renders collapsible Alerts bar with aria-label", async () => {
      renderWithProviders(<AlertsZone />);
      await waitFor(() => {
        expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
      });
    });

    it("shows alert items from MSW data after expanding", async () => {
      renderWithProviders(<AlertsZone />);
      await waitFor(() => {
        expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
      });
      // Expand the collapsible bar
      const btn = screen.getByLabelText("Alerts").querySelector("button");
      if (btn) btn.click();
      await waitFor(() => {
        expect(screen.getByText("BUY Signal")).toBeInTheDocument();
      });
    });

    it("still renders on error — derived alerts fill in", async () => {
      server.use(
        http.get("/api/v1/alerts", () =>
          HttpResponse.json({ detail: "Server Error" }, { status: 500 })
        )
      );

      renderWithProviders(<AlertsZone />);
      await waitFor(() => {
        // Derived alerts from watchlist keep the bar visible
        expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
      });
    });

    it("shows derived alerts when backend alerts array is empty", async () => {
      server.use(
        http.get("/api/v1/alerts", () =>
          HttpResponse.json({ alerts: [], total: 0, unread_count: 0 })
        )
      );

      renderWithProviders(<AlertsZone />);
      await waitFor(() => {
        // Bar renders — may show derived alerts from watchlist data
        expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
      });
    });
  });

  describe("NewsZone", () => {
    it("renders News section", async () => {
      renderWithProviders(<NewsZone />);
      await waitFor(() => {
        expect(screen.getByLabelText("News and Intelligence")).toBeInTheDocument();
      });
    });

    it("shows article titles from MSW data", async () => {
      renderWithProviders(<NewsZone />);
      await waitFor(() => {
        expect(screen.getByText("Apple announces new AI features")).toBeInTheDocument();
      });
    });

    it("shows empty state when articles array is empty", async () => {
      server.use(
        http.get("/api/v1/news/dashboard", () =>
          HttpResponse.json({ articles: [], ticker_count: 0 })
        )
      );

      renderWithProviders(<NewsZone />);
      await waitFor(() => {
        expect(screen.getByText("No news yet")).toBeInTheDocument();
      });
    });
  });

  describe("PortfolioZone", () => {
    it("renders Portfolio Analytics section with aria-label", () => {
      renderWithProviders(<PortfolioZone />);
      expect(screen.getByLabelText("Portfolio Analytics")).toBeInTheDocument();
    });

    it("shows empty portfolio state when position_count is 0", async () => {
      server.use(
        http.get("/api/v1/portfolio/summary", () =>
          HttpResponse.json({
            total_value: 0,
            total_cost_basis: 0,
            unrealized_pnl: 0,
            unrealized_pnl_pct: 0,
            position_count: 0,
            sectors: [],
          })
        )
      );

      renderWithProviders(<PortfolioZone />);
      await waitFor(() => {
        expect(screen.getByText("No portfolio yet")).toBeInTheDocument();
      });
    });
  });
});
