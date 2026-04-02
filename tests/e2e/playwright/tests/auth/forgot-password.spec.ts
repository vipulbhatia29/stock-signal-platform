import { test, expect } from "@playwright/test";

test.describe("Forgot Password", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("should show forgot password form", async ({ page }) => {
    await page.goto("/auth/forgot-password");
    await expect(page.locator("#email")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Send reset link/i })
    ).toBeVisible();
  });

  test("should show confirmation after submitting email", async ({ page }) => {
    await page.route("**/api/v1/auth/forgot-password", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ message: "Reset email sent" }),
      });
    });

    await page.goto("/auth/forgot-password");
    await page.locator("#email").fill("user@test.com");
    await page.getByRole("button", { name: /Send reset link/i }).click();
    // Should show confirmation text + back to login link
    await expect(page.getByText(/check your email|reset link/i)).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByRole("link", { name: /login/i })).toBeVisible();
  });

  test("should show success even on API error (privacy-safe)", async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/forgot-password", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal error" }),
      });
    });

    await page.goto("/auth/forgot-password");
    await page.locator("#email").fill("nonexistent@test.com");
    await page.getByRole("button", { name: /Send reset link/i }).click();
    // Privacy: always shows success regardless of backend response
    await expect(page.getByText(/check your email|reset link/i)).toBeVisible({
      timeout: 5000,
    });
  });
});
