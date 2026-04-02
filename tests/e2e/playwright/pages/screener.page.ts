import type { Locator } from "@playwright/test";

import { BasePage } from "./base.page";

/** Screener page interactions — upgraded with filter controls. */
export class ScreenerPage extends BasePage {
  async goto(): Promise<void> {
    await super.goto("/screener");
    await this.waitForLoaderGone();
  }

  get table(): Locator {
    return this.tid("screener-table");
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: /Screener/i });
  }

  get watchlistTab(): Locator {
    return this.page.getByRole("button", { name: /Watchlist/i });
  }

  get allStocksTab(): Locator {
    return this.page.getByRole("button", { name: /All Stocks/i });
  }

  get densityToggle(): Locator {
    return this.page.getByLabel(/Switch to (compact|comfortable)/i);
  }

  get viewModeToggle(): Locator {
    return this.page.getByLabel(/Switch to (grid|table)/i);
  }

  get resetButton(): Locator {
    return this.page.getByRole("button", { name: /Reset/i });
  }

  get nextPageButton(): Locator {
    return this.page.getByRole("button", { name: /Next/i });
  }

  get prevPageButton(): Locator {
    return this.page.getByRole("button", { name: /Previous/i });
  }
}
