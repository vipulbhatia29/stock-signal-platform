import { test, expect } from "@playwright/test";

test.describe("Sectors Page", () => {
  test("should render sectors page with filter tabs", async ({ page }) => {
    await page.goto("/sectors");

    // Page heading
    await expect(page.getByText("Sector Performance")).toBeVisible({
      timeout: 10000,
    });

    // Filter tabs: All, Portfolio, Watchlist
    await expect(page.getByRole("button", { name: "All" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Portfolio" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Watchlist" })
    ).toBeVisible();
  });

  test("should show empty state when no stocks tracked", async ({ page }) => {
    await page.goto("/sectors");
    await expect(
      page.getByText(/no sectors found/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test("should switch between filter tabs", async ({ page }) => {
    await page.goto("/sectors");
    await expect(page.getByText("Sector Performance")).toBeVisible({
      timeout: 10000,
    });

    // Click Portfolio tab
    await page.getByRole("button", { name: "Portfolio" }).click();
    await expect(
      page.getByRole("button", { name: "Portfolio" })
    ).toBeVisible();

    // Click Watchlist tab
    await page.getByRole("button", { name: "Watchlist" }).click();
    await expect(
      page.getByRole("button", { name: "Watchlist" })
    ).toBeVisible();

    // Click back to All
    await page.getByRole("button", { name: "All" }).click();
    await expect(page.getByRole("button", { name: "All" })).toBeVisible();
  });
});
