import { test, expect } from "@playwright/test";
import { DashboardPage } from "../../pages/dashboard.page";

test.describe("Dashboard", () => {
  test("should load dashboard page", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId("dashboard-page")).toBeVisible();
  });

  test("should display sidebar navigation", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId("sidebar-nav")).toBeVisible();
  });

  test("should display topbar", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(page.getByTestId("topbar")).toBeVisible();
  });

  test("should have refresh button", async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await expect(dashboard.refreshButton).toBeVisible();
  });
});
