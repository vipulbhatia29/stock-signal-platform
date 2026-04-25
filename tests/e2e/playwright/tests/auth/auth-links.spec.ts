import { test, expect } from "@playwright/test";

test.describe("Auth Page Links & Buttons", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("login page should have forgot password link", async ({ page }) => {
    await page.goto("/login");
    const forgotLink = page.getByRole("link", { name: /forgot password/i });
    await expect(forgotLink).toBeVisible({ timeout: 5000 });
    await forgotLink.click();
    await page.waitForURL("**/auth/forgot-password");
    expect(page.url()).toContain("/auth/forgot-password");
  });

  test("login page should have register link", async ({ page }) => {
    await page.goto("/login");
    const createLink = page.getByRole("link", { name: /create one/i });
    await expect(createLink).toBeVisible({ timeout: 5000 });
    await createLink.click();
    await page.waitForURL("**/register");
    expect(page.url()).toContain("/register");
  });

  test("login page should have Google OAuth button", async ({ page }) => {
    await page.goto("/login");
    const googleBtn = page.getByRole("button", {
      name: /continue with google/i,
    });
    await expect(googleBtn).toBeVisible({ timeout: 5000 });
  });

  test("login page should have remember me checkbox", async ({ page }) => {
    await page.goto("/login");
    const checkbox = page.getByRole("checkbox", { name: /remember me/i });
    await expect(checkbox).toBeVisible({ timeout: 5000 });
    await checkbox.click();
  });

  test("register page should have sign in link", async ({ page }) => {
    await page.goto("/register");
    const signInLink = page.getByRole("link", { name: /sign in/i });
    await expect(signInLink).toBeVisible({ timeout: 5000 });
    await signInLink.click();
    await page.waitForURL("**/login");
    expect(page.url()).toContain("/login");
  });

  test("register page should have Google OAuth button", async ({ page }) => {
    await page.goto("/register");
    const googleBtn = page.getByRole("button", {
      name: /continue with google/i,
    });
    await expect(googleBtn).toBeVisible({ timeout: 5000 });
  });
});
