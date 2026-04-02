import type { Locator, Page } from "@playwright/test";

import { BasePage } from "./base.page";

/** Stock detail page interactions. */
export class StockPage extends BasePage {
  private ticker: string;

  constructor(page: Page, ticker: string) {
    super(page);
    this.ticker = ticker;
  }

  async goto(): Promise<void> {
    await super.goto(`/stocks/${this.ticker}`);
    await this.waitForLoaderGone();
  }

  async waitForDataLoad(): Promise<void> {
    await this.page
      .locator("#sec-signals")
      .waitFor({ state: "visible", timeout: 15_000 });
  }

  get priceChart(): Locator {
    return this.page.locator("#sec-price");
  }

  get signalSection(): Locator {
    return this.page.locator("#sec-signals");
  }

  get fundamentalsSection(): Locator {
    return this.page.locator("#sec-fundamentals");
  }

  get benchmarkSection(): Locator {
    return this.page.locator("#sec-benchmark");
  }

  get headingWithTicker(): Locator {
    return this.page.getByRole("heading").filter({ hasText: this.ticker });
  }

  get watchlistButton(): Locator {
    return this.page.getByRole("button", { name: /watchlist/i });
  }

  periodButton(period: string): Locator {
    return this.page.getByRole("button", { name: period, exact: true });
  }
}
