import type { Locator } from "@playwright/test";

import { BasePage } from "./base.page";

/** Portfolio page interactions. */
export class PortfolioPage extends BasePage {
  async goto(): Promise<void> {
    await super.goto("/portfolio");
    await this.waitForLoaderGone();
  }

  get statTiles(): Locator {
    return this.tid("stat-tile");
  }

  get logTransactionButton(): Locator {
    return this.page.getByRole("button", { name: /Log Transaction/i });
  }

  async openLogTransaction(): Promise<void> {
    await this.logTransactionButton.click();
  }

  async fillTransaction(data: {
    ticker: string;
    type?: "BUY" | "SELL";
    shares: string;
    price: string;
    date: string;
  }): Promise<void> {
    await this.page.locator("#ticker").fill(data.ticker);
    if (data.type === "SELL") {
      await this.page.locator("#type").selectOption("SELL");
    }
    await this.page.locator("#shares").fill(data.shares);
    await this.page.locator("#price").fill(data.price);
    await this.page.locator("#date").fill(data.date);
  }

  async submitTransaction(): Promise<void> {
    await this.page.getByRole("button", { name: /Log Trade/i }).click();
  }

  get positionsTable(): Locator {
    return this.page.locator("table").first();
  }

  get sectorChart(): Locator {
    return this.page.locator(".recharts-wrapper").first();
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: /Portfolio/i });
  }
}
