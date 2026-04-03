import { test, expect } from "@playwright/test";

const TICKER = "AAPL";

const CONVERGENCE_RESPONSE = {
  ticker: TICKER,
  date: "2026-04-03",
  signals: [
    { signal: "rsi", direction: "bullish", value: 35.0 },
    { signal: "macd", direction: "bullish", value: 0.05 },
    { signal: "sma", direction: "bullish", value: 200.0 },
    { signal: "piotroski", direction: "bullish", value: 7 },
    { signal: "forecast", direction: "bearish", value: -0.04 },
    { signal: "news", direction: "neutral", value: 0.1 },
  ],
  signals_aligned: 4,
  convergence_label: "weak_bull",
  composite_score: 7.8,
  divergence: {
    is_divergent: true,
    forecast_direction: "bearish",
    technical_majority: "bullish",
    historical_hit_rate: 0.61,
    sample_count: 23,
  },
  rationale:
    "4 of 6 signals are bullish. However, 90-day forecast is bearish. The forecast was right 61% of the time (23 cases).",
};

test.describe("Signal Convergence", () => {
  /** Mock convergence + stock detail endpoints. */
  async function mockAPIs(page: import("@playwright/test").Page) {
    await page.route(`**/api/v1/convergence/${TICKER}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CONVERGENCE_RESPONSE),
      });
    });

    // Mock stock signals (needed by stock detail page)
    await page.route(`**/api/v1/stocks/${TICKER}/signals`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ticker: TICKER,
          signals: [],
          composite_score: 7.8,
          action: "BUY",
          computed_at: "2026-04-03T10:00:00Z",
        }),
      });
    });

    // Mock other stock detail endpoints
    await page.route(`**/api/v1/stocks/${TICKER}/prices**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route(`**/api/v1/stocks/${TICKER}`, async (route) => {
      if (route.request().url().includes("/signals") || route.request().url().includes("/prices")) {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ticker: TICKER,
          name: "Apple Inc.",
          sector: "Technology",
          exchange: "NASDAQ",
          is_active: true,
        }),
      });
    });

    await page.route("**/api/v1/forecasts/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ horizons: [], ticker_count: 0, vix_regime: "normal" }),
      });
    });

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
  }

  test("traffic light indicators render on stock detail page", async ({
    page,
  }) => {
    await mockAPIs(page);
    await page.goto(`/stocks/${TICKER}`);

    // Wait for convergence data to load
    const trafficLights = page.locator('[role="list"][aria-label="Signal convergence indicators"]');
    await expect(trafficLights).toBeVisible({ timeout: 10000 });

    // Should have 6 signal indicators
    const items = trafficLights.locator('[role="listitem"]');
    await expect(items).toHaveCount(6);
  });

  test("divergence alert renders for divergent stock", async ({ page }) => {
    await mockAPIs(page);
    await page.goto(`/stocks/${TICKER}`);

    // Divergence alert should appear
    const alert = page.locator('[role="alert"]');
    await expect(alert).toBeVisible({ timeout: 10000 });
    await expect(alert).toContainText("Signal divergence");
    await expect(alert).toContainText("61%");
  });

  test("rationale section expands on click", async ({ page }) => {
    await mockAPIs(page);
    await page.goto(`/stocks/${TICKER}`);

    // Find rationale toggle button
    const rationaleButton = page.locator('button:has-text("Signal rationale")');
    await expect(rationaleButton).toBeVisible({ timeout: 10000 });
    await expect(rationaleButton).toHaveAttribute("aria-expanded", "false");

    // Click to expand
    await rationaleButton.click();
    await expect(rationaleButton).toHaveAttribute("aria-expanded", "true");

    // Rationale text should be visible
    await expect(page.locator("text=4 of 6 signals are bullish")).toBeVisible();
  });
});
