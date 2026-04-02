import { test, expect } from "@playwright/test";

/**
 * Responsive breakpoint specs — verify layout adapts at 4 viewport widths.
 *
 * Tests that key UI elements are visible and properly sized at each breakpoint.
 */

const breakpoints = [
  { name: "XL (1920)", width: 1920, height: 1080 },
  { name: "LG (1440)", width: 1440, height: 900 },
  { name: "MD (1024)", width: 1024, height: 768 },
  { name: "SM (768)", width: 768, height: 1024 },
] as const;

for (const bp of breakpoints) {
  test.describe(`Responsive — ${bp.name}`, () => {
    test.use({ viewport: { width: bp.width, height: bp.height } });

    test("Dashboard renders without horizontal overflow", async ({ page }) => {
      await page.goto("/dashboard");
      await page.waitForLoadState("networkidle");

      // Check no horizontal scrollbar (body doesn't exceed viewport)
      const bodyWidth = await page.evaluate(
        () => document.body.scrollWidth
      );
      expect(bodyWidth).toBeLessThanOrEqual(bp.width + 1); // +1 for rounding
    });

    test("Sidebar navigation is accessible", async ({ page }) => {
      await page.goto("/dashboard");
      await page.waitForLoadState("networkidle");

      const sidebar = page.getByTestId("sidebar-nav");
      await expect(sidebar).toBeVisible();

      // On smaller viewports, sidebar may be collapsed but still present
      const box = await sidebar.boundingBox();
      expect(box).toBeTruthy();
      if (bp.width >= 1024) {
        // Desktop: sidebar should have reasonable width
        expect(box!.width).toBeGreaterThanOrEqual(48);
      }
    });

    test("Topbar spans full width", async ({ page }) => {
      await page.goto("/dashboard");
      await page.waitForLoadState("networkidle");

      const topbar = page.getByTestId("topbar");
      await expect(topbar).toBeVisible();

      const box = await topbar.boundingBox();
      expect(box).toBeTruthy();
      // Topbar should span most of the viewport (minus sidebar)
      expect(box!.width).toBeGreaterThanOrEqual(bp.width * 0.5);
    });

    test("Screener table is visible and usable", async ({ page }) => {
      await page.goto("/screener");
      await page.waitForLoadState("networkidle");

      const table = page.getByTestId("screener-table");
      await expect(table).toBeVisible({ timeout: 10000 });

      const box = await table.boundingBox();
      expect(box).toBeTruthy();
      // Table should use available width
      if (bp.width >= 1024) {
        expect(box!.width).toBeGreaterThanOrEqual(500);
      } else {
        // On smaller screens, table should still be at least 300px
        expect(box!.width).toBeGreaterThanOrEqual(300);
      }
    });
  });
}
