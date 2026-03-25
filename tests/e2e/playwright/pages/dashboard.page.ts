import type { Locator } from "@playwright/test";

import { BasePage } from "./base.page";

/** Dashboard page interactions. */
export class DashboardPage extends BasePage {
  async goto(): Promise<void> {
    await super.goto("/dashboard");
    await this.waitForLoaderGone();
  }

  /** Get all stat tiles on the dashboard. */
  get statTiles(): Locator {
    return this.tid("stat-tile");
  }

  /** Get the sidebar navigation. */
  get sidebar(): Locator {
    return this.tid("sidebar-nav");
  }

  /** Click a sidebar link by label text. */
  async navigateTo(label: string): Promise<void> {
    await this.page.getByRole("link", { name: label }).click();
  }

  /** Check if the refresh button exists. */
  get refreshButton(): Locator {
    return this.tid("refresh-all");
  }
}
