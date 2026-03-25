import { test, expect } from "@playwright/test";

test.describe("Logout", () => {
  test("should redirect to login after logout", async ({ page }) => {
    await page.goto("/dashboard");
    // The sidebar has a logout button/link
    const logoutLink = page.getByRole("link", { name: /log\s*out/i });
    if (await logoutLink.isVisible({ timeout: 3000 }).catch(() => false)) {
      await logoutLink.click();
    } else {
      // Try button variant
      const logoutBtn = page.getByRole("button", { name: /log\s*out/i });
      await logoutBtn.click();
    }
    await page.waitForURL("**/login", { timeout: 10000 });
    expect(page.url()).toContain("/login");
  });
});
