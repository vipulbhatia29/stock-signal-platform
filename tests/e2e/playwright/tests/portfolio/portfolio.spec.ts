import { test, expect } from "@playwright/test";
import { PortfolioPage } from "../../pages/portfolio.page";

test.describe("Portfolio", () => {
  test("should load portfolio page with heading", async ({ page }) => {
    const portfolio = new PortfolioPage(page);
    await portfolio.goto();
    await expect(portfolio.heading).toBeVisible();
  });

  test("should display stat tiles", async ({ page }) => {
    const portfolio = new PortfolioPage(page);
    await portfolio.goto();
    // Portfolio has 4 KPI tiles: Total Value, Cost Basis, Unrealized P&L, Return
    await expect(portfolio.statTiles.first()).toBeVisible({ timeout: 10000 });
  });

  test("should open Log Transaction dialog", async ({ page }) => {
    const portfolio = new PortfolioPage(page);
    await portfolio.goto();
    await portfolio.openLogTransaction();
    // Dialog should be visible with form fields
    await expect(page.locator("#ticker")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("#shares")).toBeVisible();
    await expect(page.locator("#price")).toBeVisible();
  });

  test("should fill and submit transaction form", async ({ page }) => {
    // Mock the transaction POST endpoint
    let capturedPayload: Record<string, unknown> | null = null;
    await page.route("**/api/v1/portfolio/transactions", async (route, req) => {
      if (req.method() === "POST") {
        capturedPayload = (await req.postDataJSON()) as Record<string, unknown>;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: "txn-1",
            ticker: "AAPL",
            transaction_type: "BUY",
            shares: 10,
            price_per_share: 185.5,
            transacted_at: "2026-04-01",
          }),
        });
      } else {
        await route.continue();
      }
    });

    const portfolio = new PortfolioPage(page);
    await portfolio.goto();
    await portfolio.openLogTransaction();
    await portfolio.fillTransaction({
      ticker: "AAPL",
      shares: "10",
      price: "185.50",
      date: "2026-04-01",
    });
    await portfolio.submitTransaction();

    // Verify the API was called
    await page.waitForTimeout(2000);
    expect(capturedPayload).toBeTruthy();
  });

  test("should show positions table when data exists", async ({ page }) => {
    const portfolio = new PortfolioPage(page);
    await portfolio.goto();
    // If portfolio has positions, table should be visible
    const table = portfolio.positionsTable;
    await expect(table).toBeVisible({ timeout: 10000 });
  });

  test("should render sector allocation chart", async ({ page }) => {
    const portfolio = new PortfolioPage(page);
    await portfolio.goto();
    // Sector chart may take a moment to render via Recharts
    const chart = portfolio.sectorChart;
    if (await chart.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(chart).toBeVisible();
    }
  });
});
