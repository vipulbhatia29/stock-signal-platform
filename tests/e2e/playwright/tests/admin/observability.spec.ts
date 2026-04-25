import { test, expect } from "@playwright/test";

test.describe("Admin Observability Dashboard", () => {
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

  /** Mock admin observability KPIs. */
  async function mockObsKpis(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/observability/admin/kpis", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          result: {
            subsystems: {
              http: { status: "healthy", detail: "p95 42ms" },
              database: { status: "healthy", detail: "pool 8/5" },
              cache: { status: "healthy", detail: "1ms 4MB" },
              external_api: { status: "healthy", detail: "ok" },
              celery: { status: "degraded", detail: "0 workers" },
              agent: { status: "healthy", detail: "ok" },
              frontend: { status: "healthy", detail: "ok" },
            },
          },
        }),
      });
    });
  }

  /** Mock admin errors endpoint. */
  async function mockObsErrors(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/observability/admin/errors*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ result: [] }),
      });
    });
  }

  /** Mock admin findings endpoint. */
  async function mockObsFindings(page: import("@playwright/test").Page) {
    await page.route(
      "**/api/v1/observability/admin/findings*",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ result: [] }),
        });
      }
    );
  }

  /** Mock admin externals endpoint. */
  async function mockObsExternals(page: import("@playwright/test").Page) {
    await page.route(
      "**/api/v1/observability/admin/externals*",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            result: {
              providers: [
                {
                  provider: "yfinance",
                  calls: 0,
                  success_rate: null,
                  p95_latency_ms: null,
                  total_cost_usd: null,
                  rate_limit_events: 0,
                },
              ],
            },
          }),
        });
      }
    );
  }

  /** Mock admin costs endpoint. */
  async function mockObsCosts(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/observability/admin/costs*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          result: { breakdown: [], top_10: [] },
        }),
      });
    });
  }

  /** Mock admin pipelines endpoint. */
  async function mockObsPipelines(page: import("@playwright/test").Page) {
    await page.route(
      "**/api/v1/observability/admin/pipelines*",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ result: { runs: [] } }),
        });
      }
    );
  }

  /** Mock admin DQ endpoint. */
  async function mockObsDq(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/observability/admin/dq*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ result: [] }),
      });
    });
  }

  /** Set up all mocks. */
  async function setupMocks(page: import("@playwright/test").Page) {
    await mockAdminUser(page);
    await mockObsKpis(page);
    await mockObsErrors(page);
    await mockObsFindings(page);
    await mockObsExternals(page);
    await mockObsCosts(page);
    await mockObsPipelines(page);
    await mockObsDq(page);
  }

  test("should render health strip with all 7 subsystems", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    await expect(page.getByText("Observability")).toBeVisible({
      timeout: 10000,
    });

    // Health strip subsystems
    await expect(page.getByText("HTTP")).toBeVisible();
    await expect(page.getByText("Database")).toBeVisible();
    await expect(page.getByText("Cache")).toBeVisible();
    await expect(page.getByText("External API")).toBeVisible();
    await expect(page.getByText("Celery")).toBeVisible();
    await expect(page.getByText("Agent")).toBeVisible();
    await expect(page.getByText("Frontend")).toBeVisible();
  });

  test("should show all 4 tabs and Overview is selected by default", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByRole("tab", { name: "APIs & Cost" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Infrastructure" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Trace Explorer" })
    ).toBeVisible();

    // Overview should be selected
    await expect(
      page.getByRole("tab", { name: "Overview", selected: true })
    ).toBeVisible();
  });

  test("should render Live Error Stream on Overview tab", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    await expect(page.getByText("Live Error Stream")).toBeVisible({
      timeout: 10000,
    });

    // Filter controls
    await expect(page.getByLabel(/filter by layer/i)).toBeVisible();
    await expect(page.getByLabel(/filter by severity/i)).toBeVisible();
  });

  test("should switch to APIs & Cost tab and show providers table", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    await page.getByRole("tab", { name: "APIs & Cost" }).click();

    await expect(page.getByText("External APIs")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Cost Breakdown")).toBeVisible();
    // Provider row
    await expect(page.getByText(/yfinance/i)).toBeVisible();
  });

  test("should switch to Infrastructure tab and show DQ scanner", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    await page.getByRole("tab", { name: "Infrastructure" }).click();

    await expect(page.getByText("Data Quality Scanner")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByRole("button", { name: "Run Now" })
    ).toBeVisible();
  });

  test("should switch to Trace Explorer tab and show trace ID input", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    await page.getByRole("tab", { name: "Trace Explorer" }).click();

    await expect(page.getByText("Trace Explorer")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByPlaceholder(/enter trace id/i)
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Load" })).toBeVisible();
  });

  test("should cycle through all tabs", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/observability");

    // Start on Overview
    await expect(page.getByText("Live Error Stream")).toBeVisible({
      timeout: 10000,
    });

    // APIs & Cost
    await page.getByRole("tab", { name: "APIs & Cost" }).click();
    await expect(page.getByText("External APIs")).toBeVisible();

    // Infrastructure
    await page.getByRole("tab", { name: "Infrastructure" }).click();
    await expect(page.getByText("Data Quality Scanner")).toBeVisible();

    // Trace Explorer
    await page.getByRole("tab", { name: "Trace Explorer" }).click();
    await expect(page.getByPlaceholder(/enter trace id/i)).toBeVisible();

    // Back to Overview
    await page.getByRole("tab", { name: "Overview" }).click();
    await expect(page.getByText("Live Error Stream")).toBeVisible();
  });
});
