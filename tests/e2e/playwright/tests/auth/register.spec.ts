import { test, expect } from "@playwright/test";
import { RegisterPage } from "../../pages/register.page";

test.describe("Register", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("should show register form", async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await expect(page.getByTestId("register-form")).toBeVisible();
    await expect(page.getByTestId("register-email")).toBeVisible();
    await expect(page.getByTestId("register-password")).toBeVisible();
    await expect(page.getByTestId("register-submit")).toBeVisible();
  });

  test("should register and redirect to login on success", async ({
    page,
  }) => {
    // Mock the register endpoint to return success
    await page.route("**/api/v1/auth/register", async (route) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "new-user", email: "new@test.com" }),
      });
    });

    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await registerPage.register("new@test.com", "StrongPass1!");
    await page.waitForURL("**/login", { timeout: 10000 });
    expect(page.url()).toContain("/login");
  });

  test("should show error on duplicate email", async ({ page }) => {
    await page.route("**/api/v1/auth/register", async (route) => {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Email already registered" }),
      });
    });

    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await registerPage.register("existing@test.com", "StrongPass1!");
    const error = await registerPage.getErrorMessage();
    expect(error).toBeTruthy();
  });

  test("should show error on weak password", async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    // Client-side validation: password < 8 chars
    await registerPage.register("test@test.com", "short");
    // Should show client-side error (not reach API)
    const error = await registerPage.getErrorMessage();
    expect(error).toBeTruthy();
  });
});
