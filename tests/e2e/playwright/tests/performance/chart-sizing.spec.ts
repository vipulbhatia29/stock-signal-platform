import { test, expect } from "@playwright/test";

/**
 * Chart sizing assertions — verify Recharts charts render at minimum
 * dimensions on desktop and mobile viewports.
 *
 * Recharts animations must be disabled via isAnimationActive={false}
 * or we must wait for animation completion before measuring.
 */

test.describe("Chart Sizing — Desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Dashboard charts render at minimum desktop dimensions", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Wait for Recharts to render (SVG elements appear)
    const charts = page.locator(".recharts-wrapper");
    const chartCount = await charts.count();

    if (chartCount > 0) {
      for (let i = 0; i < Math.min(chartCount, 5); i++) {
        const box = await charts.nth(i).boundingBox();
        if (box) {
          // Desktop: charts should be at least 200px wide and 150px tall
          expect(box.width).toBeGreaterThanOrEqual(200);
          expect(box.height).toBeGreaterThanOrEqual(150);
        }
      }
    }
  });

  test("Portfolio sector pie chart meets minimum size", async ({ page }) => {
    await page.goto("/portfolio");
    await page.waitForLoadState("networkidle");

    const pieChart = page.locator(".recharts-pie").first();
    if (await pieChart.isVisible({ timeout: 5000 }).catch(() => false)) {
      const wrapper = page.locator(".recharts-wrapper").first();
      const box = await wrapper.boundingBox();
      if (box) {
        // Pie chart: ≥ 250x250 on desktop
        expect(box.width).toBeGreaterThanOrEqual(250);
        expect(box.height).toBeGreaterThanOrEqual(250);
      }
    }
  });
});

test.describe("Chart Sizing — Mobile", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("Charts render at minimum mobile dimensions", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const charts = page.locator(".recharts-wrapper");
    const chartCount = await charts.count();

    if (chartCount > 0) {
      for (let i = 0; i < Math.min(chartCount, 3); i++) {
        const box = await charts.nth(i).boundingBox();
        if (box) {
          // Mobile: charts should be at least 150px wide and 100px tall
          expect(box.width).toBeGreaterThanOrEqual(150);
          expect(box.height).toBeGreaterThanOrEqual(100);
        }
      }
    }
  });

  test("Portfolio pie chart adapts to mobile viewport", async ({ page }) => {
    await page.goto("/portfolio");
    await page.waitForLoadState("networkidle");

    const pieChart = page.locator(".recharts-pie").first();
    if (await pieChart.isVisible({ timeout: 5000 }).catch(() => false)) {
      const wrapper = page.locator(".recharts-wrapper").first();
      const box = await wrapper.boundingBox();
      if (box) {
        // Mobile pie: ≥ 200x200
        expect(box.width).toBeGreaterThanOrEqual(200);
        expect(box.height).toBeGreaterThanOrEqual(200);
      }
    }
  });
});
