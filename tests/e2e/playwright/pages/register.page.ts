import { BasePage } from "./base.page";

/** Register page interactions. */
export class RegisterPage extends BasePage {
  async goto(): Promise<void> {
    await super.goto("/register");
  }

  async fillEmail(email: string): Promise<void> {
    await this.tid("register-email").fill(email);
  }

  async fillPassword(password: string): Promise<void> {
    await this.tid("register-password").fill(password);
  }

  async submit(): Promise<void> {
    await this.tid("register-submit").click();
  }

  async register(email: string, password: string): Promise<void> {
    await this.fillEmail(email);
    await this.fillPassword(password);
    await this.submit();
  }

  async getErrorMessage(): Promise<string | null> {
    const el = this.page.locator('[role="alert"], .text-red-400');
    if (await el.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      return el.first().textContent();
    }
    return null;
  }
}
