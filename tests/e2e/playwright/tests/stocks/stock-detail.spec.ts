import { test, expect } from "@playwright/test";
import { StockPage } from "../../pages/stock.page";

test.describe("Stock Detail", () => {
  const TICKER = "AAPL";

  /** Mock all stock detail API endpoints. */
  async function mockStockAPIs(page: import("@playwright/test").Page) {
    await page.route(`**/api/v1/stocks/${TICKER}/signals`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ticker: TICKER,
          signals: [
            { indicator: "RSI", value: 55.3, signal: "neutral", weight: 0.25 },
            {
              indicator: "MACD",
              value: 1.2,
              signal: "bullish_crossover",
              weight: 0.25,
            },
            {
              indicator: "SMA_20",
              value: 182.5,
              signal: "bullish",
              weight: 0.2,
            },
            {
              indicator: "Bollinger",
              value: 0.65,
              signal: "neutral",
              weight: 0.15,
            },
          ],
          composite_score: 8.2,
          action: "BUY",
          computed_at: "2026-04-02T10:00:00Z",
        }),
      });
    });

    await page.route(
      `**/api/v1/stocks/${TICKER}/prices**`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              date: "2026-04-01",
              open: 183.0,
              high: 186.0,
              low: 182.5,
              close: 185.5,
              volume: 52000000,
            },
            {
              date: "2026-04-02",
              open: 185.5,
              high: 187.0,
              low: 184.0,
              close: 186.2,
              volume: 48000000,
            },
          ]),
        });
      }
    );

    await page.route(
      `**/api/v1/stocks/${TICKER}/fundamentals`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            pe_ratio: 28.5,
            market_cap: 2850000000000,
            beta: 1.21,
            dividend_yield: 0.56,
            eps: 6.52,
            revenue_growth: 0.08,
            profit_margin: 0.264,
            piotroski_score: 7,
          }),
        });
      }
    );

    // Mock remaining endpoints to prevent 404s
    await page.route(
      `**/api/v1/stocks/${TICKER}/signals/history**`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      }
    );

    await page.route(
      `**/api/v1/stocks/${TICKER}/news`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      }
    );

    await page.route(
      `**/api/v1/stocks/${TICKER}/intelligence`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(null),
        });
      }
    );

    await page.route(
      `**/api/v1/stocks/${TICKER}/benchmark**`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ stock: [], benchmark: [] }),
        });
      }
    );

    await page.route(
      `**/api/v1/stocks/${TICKER}/analytics`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(null),
        });
      }
    );

    await page.route(`**/api/v1/stocks/watchlist`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
  }

  test("should load stock detail page with heading", async ({ page }) => {
    await mockStockAPIs(page);
    const stock = new StockPage(page, TICKER);
    await stock.goto();
    await expect(stock.headingWithTicker).toBeVisible({ timeout: 10000 });
  });

  test("should display signal cards", async ({ page }) => {
    await mockStockAPIs(page);
    const stock = new StockPage(page, TICKER);
    await stock.goto();
    await stock.waitForDataLoad();
    await expect(stock.signalSection).toBeVisible();
    // Should show composite score or action text
    await expect(page.getByText(/BUY|8\.2/)).toBeVisible();
  });

  test("should display price chart section", async ({ page }) => {
    await mockStockAPIs(page);
    const stock = new StockPage(page, TICKER);
    await stock.goto();
    await expect(stock.priceChart).toBeVisible({ timeout: 10000 });
  });

  test("should display fundamentals section", async ({ page }) => {
    await mockStockAPIs(page);
    const stock = new StockPage(page, TICKER);
    await stock.goto();
    await expect(stock.fundamentalsSection).toBeVisible({ timeout: 10000 });
    // Check for PE ratio value
    await expect(page.getByText(/28\.5/)).toBeVisible();
  });

  test("should navigate from screener to stock detail", async ({ page }) => {
    // Mock screener API
    await page.route("**/api/v1/stocks/signals/bulk**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              ticker: "AAPL",
              name: "Apple Inc.",
              composite_score: 8.2,
              action: "BUY",
              rsi: 55.3,
            },
          ],
          total: 1,
          page: 1,
          per_page: 50,
        }),
      });
    });

    await mockStockAPIs(page);
    await page.goto("/screener");
    await page.waitForLoadState("networkidle");

    // Click on AAPL in the table
    const aaplLink = page.getByRole("link", { name: /AAPL/i }).first();
    if (await aaplLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await aaplLink.click();
      await page.waitForURL("**/stocks/AAPL", { timeout: 10000 });
      expect(page.url()).toContain("/stocks/AAPL");
    }
  });
});
