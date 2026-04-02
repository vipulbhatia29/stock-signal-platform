import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Accessibility sweep across key pages using axe-core.
 *
 * We test for critical and serious violations only — minor issues
 * are tracked but don't fail the test.
 */
test.describe("Accessibility", () => {
  const pages = [
    { name: "Dashboard", path: "/dashboard" },
    { name: "Screener", path: "/screener" },
    { name: "Portfolio", path: "/portfolio" },
  ];

  for (const { name, path } of pages) {
    test(`${name} page should have no critical a11y violations`, async ({
      page,
    }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();

      const critical = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious"
      );

      if (critical.length > 0) {
        const summary = critical
          .map(
            (v) =>
              `[${v.impact}] ${v.id}: ${v.description} (${v.nodes.length} nodes)`
          )
          .join("\n");
        expect(critical, `A11y violations on ${name}:\n${summary}`).toEqual([]);
      }
    });
  }

  test("Login page should have no critical a11y violations", async ({
    page,
  }) => {
    // Login is unauthenticated — use empty storage state inline
    await page.context().clearCookies();
    await page.goto("/login");
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    );

    expect(critical).toEqual([]);
  });
});
