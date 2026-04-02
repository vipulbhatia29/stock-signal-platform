import { test, expect } from "@playwright/test";

test.describe("Admin Command Center", () => {
  /** Mock the /auth/me endpoint to return an admin user. */
  async function mockAdminUser(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "admin-1",
          email: "admin@test.com",
          role: "admin",
          email_verified: true,
          has_password: true,
        }),
      });
    });
  }

  /** Mock the command center data endpoint. */
  async function mockCommandCenterData(
    page: import("@playwright/test").Page
  ) {
    await page.route("**/api/v1/admin/command-center", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          system: {
            uptime_seconds: 86400,
            cpu_percent: 35.2,
            memory_percent: 62.1,
            db_pool_size: 10,
            db_pool_checked_out: 3,
            redis_connected: true,
          },
          api: {
            total_requests_24h: 15230,
            avg_latency_ms: 42.5,
            error_rate_pct: 0.3,
            top_endpoints: [
              { path: "/api/v1/stocks/signals/bulk", count: 5200, avg_ms: 38 },
              { path: "/api/v1/auth/me", count: 4100, avg_ms: 12 },
            ],
          },
          llm: {
            total_calls_24h: 342,
            total_cost_usd: 4.87,
            avg_latency_ms: 1250,
            models: [
              {
                model: "claude-sonnet-4-20250514",
                calls: 280,
                cost_usd: 3.92,
                avg_tokens: 1500,
              },
            ],
          },
          pipeline: {
            last_run: "2026-04-02T04:00:00Z",
            status: "success",
            duration_seconds: 245,
            stocks_processed: 566,
            steps: [
              {
                name: "ingest",
                status: "success",
                duration_seconds: 120,
              },
              {
                name: "signals",
                status: "success",
                duration_seconds: 95,
              },
            ],
          },
          meta: {
            generated_at: "2026-04-02T12:00:00Z",
            degraded_zones: [],
          },
        }),
      });
    });
  }

  test("should render all four command center panels", async ({ page }) => {
    await mockAdminUser(page);
    await mockCommandCenterData(page);
    await page.goto("/admin/command-center");

    await expect(page.getByTestId("system-health-panel")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByTestId("api-traffic-panel")).toBeVisible();
    await expect(page.getByTestId("llm-operations-panel")).toBeVisible();
    await expect(page.getByTestId("pipeline-panel")).toBeVisible();
  });

  test("should show metric cards with data", async ({ page }) => {
    await mockAdminUser(page);
    await mockCommandCenterData(page);
    await page.goto("/admin/command-center");

    // Should display metric cards within panels
    await expect(page.getByTestId("metric-card").first()).toBeVisible({
      timeout: 10000,
    });
    // Check specific data appears
    await expect(page.getByText(/15,?230|15230/)).toBeVisible();
  });
});
