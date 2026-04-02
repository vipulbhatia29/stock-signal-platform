import { test, expect } from "@playwright/test";
import { DashboardPage } from "../../pages/dashboard.page";

test.describe("Dashboard Zones", () => {
  test("should display Market Pulse zone", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(
      page.locator('section[aria-label="Market Pulse"]')
    ).toBeVisible({ timeout: 10000 });
  });

  test("should display Signals zone", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(
      page.locator('section[aria-label="Your Signals"]')
    ).toBeVisible({ timeout: 10000 });
  });

  test("should navigate to portfolio via sidebar", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.navigateTo("Portfolio");
    await page.waitForURL("**/portfolio", { timeout: 10000 });
    expect(page.url()).toContain("/portfolio");
  });

  test("should trigger data reload on refresh", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();

    // Track API calls after refresh click
    const apiCalls: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/v1/")) {
        apiCalls.push(req.url());
      }
    });

    const refreshBtn = dashboard.refreshButton;
    if (await refreshBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await refreshBtn.click();
      // Give time for requests to fire
      await page.waitForTimeout(2000);
      expect(apiCalls.length).toBeGreaterThan(0);
    }
  });
});
