import { test, expect } from "@playwright/test";

test.describe("No Backend Leaks", () => {
  test("should not expose API keys or tokens in DOM", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    const html = await page.content();

    // Check for common secret patterns in rendered HTML
    const secretPatterns = [
      /sk-[a-zA-Z0-9]{20,}/,           // OpenAI-style keys
      /Bearer\s+[a-zA-Z0-9._-]{20,}/,  // Bearer tokens
      /api[_-]?key['":\s]*[a-zA-Z0-9]{20,}/i, // Generic API keys
      /secret['":\s]*[a-zA-Z0-9]{20,}/i,       // Generic secrets
    ];

    for (const pattern of secretPatterns) {
      expect(html).not.toMatch(pattern);
    }
  });

  test("should not serve sourcemaps in production", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    const html = await page.content();

    // Check script tags don't reference .map files
    const scripts = await page.locator("script[src]").all();
    for (const script of scripts) {
      const src = await script.getAttribute("src");
      if (src) {
        expect(src).not.toMatch(/\.map$/);
      }
    }

    // Check no sourceMappingURL comments in inline scripts
    expect(html).not.toContain("sourceMappingURL");
  });

  test("should include security headers", async ({ page }) => {
    const response = await page.goto("/dashboard");
    expect(response).toBeTruthy();
    const headers = response!.headers();

    // X-Content-Type-Options prevents MIME sniffing
    expect(headers["x-content-type-options"]).toBe("nosniff");
  });

  test("should have no console errors on dashboard load", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Filter out known benign errors (e.g., favicon 404)
    const realErrors = consoleErrors.filter(
      (msg) => !msg.includes("favicon") && !msg.includes("404")
    );
    expect(realErrors).toEqual([]);
  });

  test("should not make requests to external domains", async ({ page }) => {
    const externalRequests: string[] = [];
    page.on("request", (req) => {
      const url = new URL(req.url());
      const allowedHosts = ["localhost", "127.0.0.1"];
      if (!allowedHosts.includes(url.hostname)) {
        externalRequests.push(req.url());
      }
    });

    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Allow known CDN/font domains if needed, but flag unknown external calls
    const suspicious = externalRequests.filter(
      (url) =>
        !url.includes("fonts.googleapis.com") &&
        !url.includes("fonts.gstatic.com")
    );
    expect(suspicious).toEqual([]);
  });
});
