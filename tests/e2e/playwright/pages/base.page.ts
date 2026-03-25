import type { Locator, Page } from "@playwright/test";

/** Abstract base page with shared helpers. */
export abstract class BasePage {
  constructor(protected readonly page: Page) {}

  /** Navigate to a path (relative to baseURL). */
  async goto(path: string): Promise<void> {
    await this.page.goto(path);
  }

  /** Locate element by data-testid. */
  tid(testId: string): Locator {
    return this.page.getByTestId(testId);
  }

  /** Wait for the page to finish loading (no spinners visible). */
  async waitForLoaderGone(): Promise<void> {
    const loader = this.page.locator('[data-testid="loading-spinner"]');
    if (await loader.isVisible({ timeout: 1000 }).catch(() => false)) {
      await loader.waitFor({ state: "hidden", timeout: 10_000 });
    }
  }

  /** Get current URL path. */
  get currentPath(): string {
    return new URL(this.page.url()).pathname;
  }
}
