import { test, expect } from "@playwright/test";

test.describe("Protected Route Redirects", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("unauthenticated /dashboard redirects to /login", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForURL("**/login", { timeout: 10000 });
    expect(page.url()).toContain("/login");
  });

  test("unauthenticated /portfolio redirects to /login", async ({ page }) => {
    await page.goto("/portfolio");
    await page.waitForURL("**/login", { timeout: 10000 });
    expect(page.url()).toContain("/login");
  });
});
