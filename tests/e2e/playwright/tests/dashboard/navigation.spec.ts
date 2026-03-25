import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("should navigate to screener", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByRole("link", { name: /screener/i }).click();
    await page.waitForURL("**/screener", { timeout: 5000 });
    expect(page.url()).toContain("/screener");
  });

  test("should navigate to portfolio", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByRole("link", { name: /portfolio/i }).click();
    await page.waitForURL("**/portfolio", { timeout: 5000 });
    expect(page.url()).toContain("/portfolio");
  });

  test("should navigate to sectors", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByRole("link", { name: /sector/i }).click();
    await page.waitForURL("**/sectors", { timeout: 5000 });
    expect(page.url()).toContain("/sectors");
  });
});
