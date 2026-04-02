import { test, expect } from "@playwright/test";

/**
 * CDP heap tracking — verify no significant memory leaks during navigation.
 *
 * Navigates through 5 app pages and measures JS heap growth.
 * Threshold: < 20MB growth from initial baseline.
 */

test.describe("Memory — CDP Heap Tracking", () => {
  test("JS heap growth < 20MB after 5 navigation cycles", async ({
    browser,
  }) => {
    // Create a context with CDP access
    const context = await browser.newContext();
    const page = await context.newPage();

    // Login first
    await page.goto("http://localhost:3000/login");
    await page.getByTestId("login-email").fill("e2e@test.com");
    await page.getByTestId("login-password").fill("TestPass1!");
    await page.getByTestId("login-submit").click();
    await page.waitForURL("**/dashboard", { timeout: 10000 });

    // Get CDP session for memory measurement
    const client = await context.newCDPSession(page);

    // Force initial GC and measure baseline
    await client.send("HeapProfiler.collectGarbage");
    const baselineMetrics = await client.send("Performance.getMetrics");
    const baselineHeap = baselineMetrics.metrics.find(
      (m) => m.name === "JSHeapUsedSize"
    );
    expect(baselineHeap).toBeTruthy();
    const baselineBytes = baselineHeap!.value;

    // Navigate through 5 pages
    const routes = [
      "/screener",
      "/portfolio",
      "/dashboard",
      "/screener",
      "/portfolio",
    ];

    for (const route of routes) {
      await page.goto(`http://localhost:3000${route}`);
      await page.waitForLoadState("networkidle");
      // Small wait for React to settle
      await page.waitForTimeout(500);
    }

    // Force GC and measure final heap
    await client.send("HeapProfiler.collectGarbage");
    const finalMetrics = await client.send("Performance.getMetrics");
    const finalHeap = finalMetrics.metrics.find(
      (m) => m.name === "JSHeapUsedSize"
    );
    expect(finalHeap).toBeTruthy();
    const finalBytes = finalHeap!.value;

    const growthMB = (finalBytes - baselineBytes) / (1024 * 1024);

    // Threshold: < 20MB growth
    expect(growthMB).toBeLessThan(20);

    await client.detach();
    await context.close();
  });
});
