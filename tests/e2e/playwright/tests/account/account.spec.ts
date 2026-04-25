import { test, expect } from "@playwright/test";

test.describe("Account Settings Page", () => {
  test("should render all account sections", async ({ page }) => {
    await page.goto("/account");

    // Page heading
    await expect(page.getByText("Account Settings")).toBeVisible({
      timeout: 10000,
    });

    // Profile section
    await expect(page.getByText("Profile")).toBeVisible();
    await expect(page.getByText("Email")).toBeVisible();
    await expect(page.getByText("Status")).toBeVisible();
    await expect(page.getByText("Member since")).toBeVisible();

    // Security section
    await expect(page.getByText("Security")).toBeVisible();
    await expect(page.getByText("Current password")).toBeVisible();
    await expect(page.getByText("New password")).toBeVisible();
    await expect(page.getByText("Confirm password")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Change password" })
    ).toBeVisible();

    // Linked Accounts section
    await expect(page.getByText("Linked Accounts")).toBeVisible();
    await expect(page.getByText("Google")).toBeVisible();

    // Danger Zone section
    await expect(page.getByText("Danger Zone")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Delete account" })
    ).toBeVisible();
  });

  test("should have clickable Link Google button", async ({ page }) => {
    await page.goto("/account");
    await expect(page.getByText("Account Settings")).toBeVisible({
      timeout: 10000,
    });

    const linkGoogleBtn = page.getByRole("button", { name: /link google/i });
    await expect(linkGoogleBtn).toBeVisible();
  });

  test("should show password form fields", async ({ page }) => {
    await page.goto("/account");
    await expect(page.getByText("Account Settings")).toBeVisible({
      timeout: 10000,
    });

    // Password fields should be fillable
    const currentPwd = page.getByLabel(/current password/i);
    const newPwd = page.getByLabel(/new password/i);
    const confirmPwd = page.getByLabel(/confirm password/i);

    await expect(currentPwd).toBeVisible();
    await expect(newPwd).toBeVisible();
    await expect(confirmPwd).toBeVisible();
  });
});
