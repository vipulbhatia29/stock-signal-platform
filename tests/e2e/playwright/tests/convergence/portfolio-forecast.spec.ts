import { test, expect } from "@playwright/test";

const PORTFOLIO_ID = "portfolio-1";

const FORECAST_RESPONSE = {
  portfolio_id: PORTFOLIO_ID,
  forecast_date: "2026-04-03",
  horizon_days: 90,
  bl: {
    portfolio_expected_return: 0.125,
    risk_free_rate: 0.05,
    per_ticker: [
      { ticker: "AAPL", expected_return: 0.18, view_confidence: 0.8 },
      { ticker: "MSFT", expected_return: 0.15, view_confidence: 0.7 },
    ],
  },
  monte_carlo: {
    simulation_days: 90,
    initial_value: 100000,
    terminal_median: 103200,
    terminal_p5: 88500,
    terminal_p95: 118900,
    bands: {
      p5: [100000, 97000, 94000, 88500],
      p25: [100000, 99000, 98000, 96500],
      p50: [100000, 101000, 102000, 103200],
      p75: [100000, 103000, 106000, 110000],
      p95: [100000, 106000, 112000, 118900],
    },
  },
  cvar: {
    cvar_95_pct: -12.5,
    cvar_99_pct: -18.3,
    var_95_pct: -8.2,
    var_99_pct: -14.1,
    description_95: "In a bad month (1-in-20): -12.5%",
    description_99: "In a very bad month (1-in-100): -18.3%",
  },
};

test.describe("Portfolio Forecast", () => {
  /** Mock portfolio + forecast endpoints. */
  async function mockAPIs(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "user-1",
          email: "e2e@test.com",
          role: "user",
          email_verified: true,
          has_password: true,
          created_at: "2025-01-01T00:00:00Z",
        }),
      });
    });

    await page.route("**/api/v1/portfolio/summary", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          portfolio_id: PORTFOLIO_ID,
          total_value: 100000,
          total_cost_basis: 90000,
          unrealized_pnl: 10000,
          unrealized_pnl_pct: 11.1,
          position_count: 2,
          sectors: [],
        }),
      });
    });

    await page.route("**/api/v1/portfolio/positions**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/v1/portfolio/history**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/v1/portfolio/rebalancing**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ total_value: 0, available_cash: 0, suggestions: [] }),
      });
    });

    await page.route(`**/api/v1/portfolio/${PORTFOLIO_ID}/forecast**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FORECAST_RESPONSE),
      });
    });

    await page.route(`**/api/v1/convergence/portfolio/${PORTFOLIO_ID}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          portfolio_id: PORTFOLIO_ID,
          date: "2026-04-03",
          positions: [],
          bullish_pct: 0.6,
          bearish_pct: 0.3,
          mixed_pct: 0.1,
          divergent_positions: [],
        }),
      });
    });

    // Catch-all for other portfolio endpoints
    await page.route("**/api/v1/portfolio/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
  }

  test("BL forecast card shows expected return", async ({ page }) => {
    await mockAPIs(page);
    await page.goto("/portfolio");

    // BL card should show the expected return
    await expect(page.locator("text=+12.5%")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=BL Expected Return")).toBeVisible();
  });

  test("CVaR card shows risk levels", async ({ page }) => {
    await mockAPIs(page);
    await page.goto("/portfolio");

    await expect(page.locator("text=In a bad month")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=-12.5%")).toBeVisible();
    await expect(page.locator("text=In a very bad month")).toBeVisible();
    await expect(page.locator("text=-18.3%")).toBeVisible();
  });

  test("Monte Carlo chart section renders", async ({ page }) => {
    await mockAPIs(page);
    await page.goto("/portfolio");

    await expect(page.locator("text=Monte Carlo Simulation")).toBeVisible({
      timeout: 10000,
    });
    // Check terminal values
    await expect(page.locator("text=median outcome")).toBeVisible();
  });
});
