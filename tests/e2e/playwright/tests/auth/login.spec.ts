import { test, expect } from "@playwright/test";
import { LoginPage } from "../../pages/login.page";

test.describe("Login", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("should show login form", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await expect(page.getByTestId("login-form")).toBeVisible();
    await expect(page.getByTestId("login-email")).toBeVisible();
    await expect(page.getByTestId("login-password")).toBeVisible();
    await expect(page.getByTestId("login-submit")).toBeVisible();
  });

  test("should show error on invalid credentials", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("wrong@email.com", "WrongPass1!");
    await expect(page.getByTestId("login-error")).toBeVisible({
      timeout: 5000,
    });
  });

  test("should redirect to dashboard on valid login", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login("e2e@test.com", "TestPass1!");
    await page.waitForURL("**/dashboard", { timeout: 10000 });
    expect(page.url()).toContain("/dashboard");
  });
});
