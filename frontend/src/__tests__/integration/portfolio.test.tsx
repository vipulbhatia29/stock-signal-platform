/**
 * Portfolio integration tests — MSW-based.
 *
 * Tests the PortfolioClient component with live MSW interceptors,
 * validating the full fetch → render pipeline for positions, stat tiles, etc.
 */

import React from "react";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders, server } from "../test-utils";

// ── Module mocks (non-network dependencies) ──────────────────────────────────

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/portfolio",
}));

jest.mock("sonner", () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
    info: jest.fn(),
    loading: jest.fn(),
  },
}));

jest.mock("@/components/motion-primitives", () => ({
  PageTransition: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

// Recharts doesn't work in jsdom — mock responsive containers
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  PieChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="pie-chart">{children}</div>
  ),
  Pie: () => <div data-testid="pie" />,
  Cell: () => null,
  Tooltip: () => null,
  Legend: () => null,
  AreaChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="area-chart">{children}</div>
  ),
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
}));

jest.mock("@/components/portfolio-value-chart", () => ({
  PortfolioValueChart: () => <div data-testid="portfolio-value-chart" />,
}));

jest.mock("@/components/portfolio-settings-sheet", () => ({
  PortfolioSettingsSheet: () => <div data-testid="portfolio-settings-sheet" />,
}));

jest.mock("@/components/rebalancing-panel", () => ({
  RebalancingPanel: () => <div data-testid="rebalancing-panel" />,
}));

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import { PortfolioClient } from "@/app/(authenticated)/portfolio/portfolio-client";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Portfolio integration — MSW", () => {
  it("renders stat tiles (Total Value, Cost Basis, P&L, Return) from MSW data", async () => {
    renderWithProviders(<PortfolioClient />);

    await waitFor(() => {
      // StatTile labels from KpiRow — use getAllByText since same text may appear in table headers too
      expect(screen.getAllByText("Total Value").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Cost Basis").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Unrealized P&L").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Return").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders positions table with mock ticker data", async () => {
    renderWithProviders(<PortfolioClient />);

    await waitFor(() => {
      // Positions from MSW handler: AAPL, MSFT, JNJ
      // Use getAllByText since tickers may appear in multiple table rows (positions + transactions)
      expect(screen.getAllByText("AAPL").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("MSFT").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("JNJ").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows empty positions message when positions array is empty", async () => {
    server.use(
      http.get("/api/v1/portfolio/positions", () =>
        HttpResponse.json([])
      )
    );

    renderWithProviders(<PortfolioClient />);

    await waitFor(() => {
      expect(
        screen.getByText("No open positions. Log a BUY transaction to get started.")
      ).toBeInTheDocument();
    });
  });
});
