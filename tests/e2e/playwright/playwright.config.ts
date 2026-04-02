import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : 3,
  reporter: process.env.CI
    ? [["html", { open: "never" }], ["github"]]
    : [["html", { open: "on-failure" }]],
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "setup",
      testMatch: /.*\.setup\.ts/,
      testDir: "./setup",
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
      },
      testIgnore: /performance|responsive/,
      dependencies: ["setup"],
    },
    {
      name: "nightly",
      testDir: "./tests",
      testMatch: /performance|responsive/,
      timeout: 120_000,
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/user.json",
      },
      dependencies: ["setup"],
    },
  ],
  webServer: process.env.CI
    ? undefined
    : [
        {
          command:
            "cd ../../.. && uv run uvicorn backend.main:app --port 8181",
          url: "http://localhost:8181/api/v1/health",
          timeout: 60_000,
          reuseExistingServer: true,
        },
        {
          command: "cd ../../../frontend && npm run build && npm start",
          url: "http://localhost:3000",
          timeout: 120_000,
          reuseExistingServer: true,
        },
      ],
});
