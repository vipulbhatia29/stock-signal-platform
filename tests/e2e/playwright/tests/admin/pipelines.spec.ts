import { test, expect } from "@playwright/test";

test.describe("Admin Pipeline Control", () => {
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

  /** Mock the pipeline groups endpoint. */
  async function mockPipelineGroups(page: import("@playwright/test").Page) {
    await page.route(
      "**/api/v1/admin/pipelines/groups",
      async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([
              {
                name: "seed",
                tasks: [
                  { name: "ingest_prices", description: "Ingest stock prices" },
                  { name: "compute_signals", description: "Compute signals" },
                ],
                execution_plan: [
                  ["ingest_prices"],
                  ["compute_signals"],
                ],
              },
              {
                name: "nightly",
                tasks: [
                  { name: "refresh_all", description: "Refresh all data" },
                  { name: "forecasts", description: "Run forecasts" },
                  { name: "alerts", description: "Check alert triggers" },
                ],
                execution_plan: [
                  ["refresh_all"],
                  ["forecasts", "alerts"],
                ],
              },
              {
                name: "maintenance",
                tasks: [
                  { name: "cleanup", description: "Cleanup old data" },
                ],
                execution_plan: [["cleanup"]],
              },
            ]),
          });
        } else {
          await route.continue();
        }
      }
    );
  }

  /** Mock active runs endpoint. */
  async function mockActiveRuns(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/admin/pipelines/groups/*/runs*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
  }

  async function setupMocks(page: import("@playwright/test").Page) {
    await mockAdminUser(page);
    await mockPipelineGroups(page);
    await mockActiveRuns(page);
  }

  test("should render Pipeline Control page with all groups", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/pipelines");

    await expect(page.getByText("Pipeline Control")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText(/manage background task groups/i)
    ).toBeVisible();

    // Task groups should be listed
    await expect(page.getByText("Seed")).toBeVisible();
    await expect(page.getByText("Nightly")).toBeVisible();
    await expect(page.getByText("Maintenance")).toBeVisible();
  });

  test("should show Run All buttons for each group", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/pipelines");

    await expect(page.getByText("Pipeline Control")).toBeVisible({
      timeout: 10000,
    });

    // Each group should have a Run All button
    const runButtons = page.getByRole("button", { name: /run all/i });
    await expect(runButtons.first()).toBeVisible();
    expect(await runButtons.count()).toBeGreaterThanOrEqual(3);
  });

  test("should expand a group to show tasks by phase", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/pipelines");

    await expect(page.getByText("Pipeline Control")).toBeVisible({
      timeout: 10000,
    });

    // Click on the Seed group to expand it
    await page.getByText("Seed").click();

    // Should show phase info and task names
    await expect(page.getByText("Phase 1")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/ingest_prices/)).toBeVisible();
  });

  test("should collapse an expanded group", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/pipelines");

    await expect(page.getByText("Pipeline Control")).toBeVisible({
      timeout: 10000,
    });

    // Expand
    await page.getByText("Seed").click();
    await expect(page.getByText("Phase 1")).toBeVisible({ timeout: 5000 });

    // Collapse
    await page.getByText("Seed").click();
    await expect(page.getByText("Phase 1")).not.toBeVisible({ timeout: 3000 });
  });

  test("should show cache controls section", async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/pipelines");

    await expect(page.getByText("Pipeline Control")).toBeVisible({
      timeout: 10000,
    });

    // Cache controls
    await expect(page.getByText(/cache controls/i)).toBeVisible();
    await expect(page.getByText(/clear all caches/i)).toBeVisible();
  });

  test("should show run history placeholder when no group selected", async ({
    page,
  }) => {
    await setupMocks(page);
    await page.goto("/admin/pipelines");

    await expect(page.getByText("Pipeline Control")).toBeVisible({
      timeout: 10000,
    });

    await expect(
      page.getByText(/select a group to view run history/i)
    ).toBeVisible();
  });
});
