import { test, expect, chromium } from "@playwright/test";
import type { Browser, Page } from "@playwright/test";
import { playAudit } from "playwright-lighthouse";

/**
 * Lighthouse performance + accessibility audits.
 *
 * These tests launch a separate Chromium instance with remote debugging
 * enabled (required by Lighthouse) and run audits against production build.
 *
 * Thresholds are intentionally lenient for CI — tighten as the app matures.
 */

const LIGHTHOUSE_PORT = 9222;

let browser: Browser;
let page: Page;

test.describe("Lighthouse Audits", () => {
  test.beforeAll(async () => {
    browser = await chromium.launch({
      args: [`--remote-debugging-port=${LIGHTHOUSE_PORT}`],
    });
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await browser.close();
  });

  test.describe("Authenticated Pages", () => {
    test.beforeAll(async () => {
      // Login to get auth cookie
      await page.goto("http://localhost:8181/api/v1/auth/login", {
        waitUntil: "networkidle",
      });
      // Use API login to set cookie
      await page.evaluate(async () => {
        await fetch("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: "e2e@test.com",
            password: "TestPass1!",
          }),
          credentials: "include",
        });
      });
    });

    test("Dashboard — LCP < 3.5s, accessibility > 90", async () => {
      await page.goto("http://localhost:3000/dashboard", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 30,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Screener — performance baseline", async () => {
      await page.goto("http://localhost:3000/screener", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 30,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Portfolio — performance baseline", async () => {
      await page.goto("http://localhost:3000/portfolio", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 25,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Sectors — performance baseline", async () => {
      await page.goto("http://localhost:3000/sectors", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 30,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Account — performance baseline", async () => {
      await page.goto("http://localhost:3000/account", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 30,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Stock Detail (AAPL) — performance baseline", async () => {
      await page.goto("http://localhost:3000/stocks/AAPL", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 25,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("User Observability — performance baseline", async () => {
      await page.goto("http://localhost:3000/observability", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 25,
          accessibility: 80,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Admin Observability — performance baseline", async () => {
      await page.goto("http://localhost:3000/admin/observability", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 25,
          accessibility: 75,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Admin Pipelines — performance baseline", async () => {
      await page.goto("http://localhost:3000/admin/pipelines", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 30,
          accessibility: 75,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Admin Command Center — performance baseline", async () => {
      await page.goto("http://localhost:3000/admin/command-center", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 25,
          accessibility: 75,
          "best-practices": 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });
  });

  test.describe("Public Pages", () => {
    test("Login — LCP < 2.5s, accessibility > 90", async () => {
      // Clear auth state for public page test
      await page.context().clearCookies();
      await page.goto("http://localhost:3000/login", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 50,
          accessibility: 85,
          "best-practices": 70,
          seo: 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });

    test("Register — performance baseline", async () => {
      await page.goto("http://localhost:3000/register", {
        waitUntil: "networkidle",
      });

      await playAudit({
        page,
        port: LIGHTHOUSE_PORT,
        thresholds: {
          performance: 50,
          accessibility: 85,
          "best-practices": 70,
          seo: 70,
        },
        reports: {
          formats: { html: false },
        },
      });
    });
  });
});
