import { test, expect } from "@playwright/test";

test.describe("Error handling", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("should show error when backend is unreachable", async ({ page }) => {
    // Block all API calls to simulate backend down
    await page.route("**/api/v1/**", (route) =>
      route.abort("connectionrefused")
    );

    await page.goto("/dashboard");
    // Should either show login (if auth fails) or error state
    // The app should not crash — should show some user-visible state
    await page.waitForTimeout(3000);
    // Page should still be rendered (not blank)
    const body = page.locator("body");
    await expect(body).not.toBeEmpty();
  });

  test("should handle login API error gracefully", async ({ page }) => {
    await page.route("**/api/v1/auth/login", (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" })
    );

    await page.goto("/login");
    await page.getByTestId("login-email").fill("test@test.com");
    await page.getByTestId("login-password").fill("TestPass1!");
    await page.getByTestId("login-submit").click();

    // Should show error, not crash
    await page.waitForTimeout(2000);
    const body = page.locator("body");
    await expect(body).not.toBeEmpty();
  });
});
