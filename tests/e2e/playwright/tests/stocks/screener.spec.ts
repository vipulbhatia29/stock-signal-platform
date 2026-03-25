import { test, expect } from "@playwright/test";

test.describe("Screener", () => {
  test("should load screener page", async ({ page }) => {
    await page.goto("/screener");
    await expect(page.getByTestId("screener-table")).toBeVisible({
      timeout: 10000,
    });
  });

  test("should display stock rows", async ({ page }) => {
    await page.goto("/screener");
    await expect(page.getByTestId("screener-table")).toBeVisible({
      timeout: 10000,
    });
    // Table should have at least header row
    const rows = page.locator("table tr, [data-testid='screener-table'] > div");
    await expect(rows.first()).toBeVisible();
  });
});
