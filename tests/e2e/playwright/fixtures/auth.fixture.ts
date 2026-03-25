import { test as base, type Page } from "@playwright/test";

/** Authenticated test fixture — uses storageState from auth.setup.ts */
export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    // storageState is already loaded via project config
    await use(page);
  },
});

export { expect } from "@playwright/test";
