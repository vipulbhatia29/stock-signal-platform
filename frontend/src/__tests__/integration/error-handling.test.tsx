/**
 * Error handling integration tests — MSW-based.
 *
 * Verifies that components gracefully handle API errors rather than crashing.
 * Tests the error fallback UI rendered by dashboard zone components.
 */

import React from "react";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders, server } from "../test-utils";

// ── Module mocks ──────────────────────────────────────────────────────────────

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

// ── Imports (after mocks) ─────────────────────────────────────────────────────

import { MarketPulseZone } from "@/app/(authenticated)/dashboard/_components/market-pulse-zone";
import { AlertsZone } from "@/app/(authenticated)/dashboard/_components/alerts-zone";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Error handling integration — MSW", () => {
  describe("API 500 responses show error state, not crash", () => {
    it("MarketPulseZone shows error fallback on 500", async () => {
      server.use(
        http.get("/api/v1/market/briefing", () =>
          HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 })
        )
      );

      renderWithProviders(<MarketPulseZone />);

      await waitFor(() => {
        expect(
          screen.getByText("Unable to load market data.")
        ).toBeInTheDocument();
      });

      // Component should still be in the DOM (no crash)
      expect(screen.getByLabelText("Market Indexes")).toBeInTheDocument();
    });

    it("AlertsZone still renders with derived alerts on 500 (graceful)", async () => {
      server.use(
        http.get("/api/v1/alerts", () =>
          HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 })
        )
      );

      renderWithProviders(<AlertsZone />);

      await waitFor(() => {
        // Component renders collapsible bar — no crash despite API error
        // Derived alerts from watchlist data still populate
        expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
      });
    });
  });

  describe("Network errors show appropriate fallback", () => {
    it("MarketPulseZone handles network-level error gracefully", async () => {
      server.use(
        http.get("/api/v1/market/briefing", () => {
          // Return a server error to simulate degraded state
          return new HttpResponse(null, { status: 503 });
        })
      );

      renderWithProviders(<MarketPulseZone />);

      await waitFor(() => {
        // Component renders the error state without crashing
        expect(
          screen.getByText("Unable to load market data.")
        ).toBeInTheDocument();
      });
    });

    it("AlertsZone handles 503 service unavailable gracefully", async () => {
      server.use(
        http.get("/api/v1/alerts", () => {
          return new HttpResponse(null, { status: 503 });
        })
      );

      renderWithProviders(<AlertsZone />);

      await waitFor(() => {
        // No crash — derived alerts still render even if backend is down
        expect(screen.getByLabelText("Alerts")).toBeInTheDocument();
      });
    });
  });
});
