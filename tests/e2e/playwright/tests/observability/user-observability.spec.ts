import { test, expect } from "@playwright/test";

test.describe("User Observability Page", () => {
  /** Mock observability KPIs. */
  async function mockObsKpis(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/observability/kpis*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          queries_today: 5,
          avg_latency_ms: 1200,
          avg_cost_per_query: 0.0142,
          pass_rate: 0.85,
          fallback_rate: 0.05,
        }),
      });
    });
  }

  /** Mock observability queries. */
  async function mockObsQueries(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/observability/queries*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ queries: [], total: 0, page: 1 }),
      });
    });
  }

  /** Mock grouped queries. */
  async function mockObsGrouped(page: import("@playwright/test").Page) {
    await page.route(
      "**/api/v1/observability/queries/grouped*",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ groups: [] }),
        });
      }
    );
  }

  async function setupMocks(page: import("@playwright/test").Page) {
    await mockObsKpis(page);
    await mockObsQueries(page);
    await mockObsGrouped(page);
  }

  test("should render AI Agent Metrics strip", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Observability")).toBeVisible({
      timeout: 10000,
    });

    // KPI cards
    await expect(page.getByText(/queries today/i)).toBeVisible();
    await expect(page.getByText(/avg latency/i)).toBeVisible();
    await expect(page.getByText(/avg cost/i)).toBeVisible();
    await expect(page.getByText(/pass rate/i)).toBeVisible();
    await expect(page.getByText(/fallback rate/i)).toBeVisible();
  });

  test("should render Usage Analytics tabs", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Usage Analytics")).toBeVisible({
      timeout: 10000,
    });

    // Analytics dimension tabs
    await expect(page.getByText("Over Time")).toBeVisible();
    await expect(page.getByText("By Model")).toBeVisible();
    await expect(page.getByText("By Provider")).toBeVisible();
    await expect(page.getByText("By Agent")).toBeVisible();
    await expect(page.getByText("By Status")).toBeVisible();
    await expect(page.getByText("By Tool")).toBeVisible();
  });

  test("should click through analytics dimension tabs", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Usage Analytics")).toBeVisible({
      timeout: 10000,
    });

    // Click through each tab
    await page.getByText("By Model").click();
    await page.getByText("By Provider").click();
    await page.getByText("By Agent").click();
    await page.getByText("By Status").click();
    await page.getByText("By Tool").click();
    await page.getByText("Over Time").click();
  });

  test("should render time range selectors", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Usage Analytics")).toBeVisible({
      timeout: 10000,
    });

    // Granularity: Day, Week, Month
    await expect(page.getByRole("button", { name: "Day" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Week" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Month" })).toBeVisible();

    // Range: 7d, 30d, 90d
    await expect(page.getByRole("button", { name: "7d" })).toBeVisible();
    await expect(page.getByRole("button", { name: "30d" })).toBeVisible();
    await expect(page.getByRole("button", { name: "90d" })).toBeVisible();
  });

  test("should switch time granularity", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Usage Analytics")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: "Week" }).click();
    await page.getByRole("button", { name: "Month" }).click();
    await page.getByRole("button", { name: "Day" }).click();
  });

  test("should render Query History section with filters", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Query History")).toBeVisible({
      timeout: 10000,
    });

    // Filter tabs
    await expect(page.getByText("All")).toBeVisible();
    await expect(page.getByText("Completed")).toBeVisible();
    await expect(page.getByText("Error")).toBeVisible();
    await expect(page.getByText("Declined")).toBeVisible();
    await expect(page.getByText("Timeout")).toBeVisible();
  });

  test("should click through query history filter tabs", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("Query History")).toBeVisible({
      timeout: 10000,
    });

    await page.getByText("Completed").click();
    await page.getByText("Error").click();
    await page.getByText("Declined").click();
    await page.getByText("Timeout").click();
    await page.getByText("All").click();
  });

  test("should render AI Quality section", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/observability");

    await expect(page.getByText("AI Quality")).toBeVisible({
      timeout: 10000,
    });
  });
});
