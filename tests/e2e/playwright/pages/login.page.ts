import { BasePage } from "./base.page";

/** Login page interactions. */
export class LoginPage extends BasePage {
  async goto(): Promise<void> {
    await super.goto("/login");
  }

  async fillEmail(email: string): Promise<void> {
    await this.tid("login-email").fill(email);
  }

  async fillPassword(password: string): Promise<void> {
    await this.tid("login-password").fill(password);
  }

  async submit(): Promise<void> {
    await this.tid("login-submit").click();
  }

  async login(email: string, password: string): Promise<void> {
    await this.fillEmail(email);
    await this.fillPassword(password);
    await this.submit();
  }

  async getErrorMessage(): Promise<string | null> {
    const el = this.tid("login-error");
    if (await el.isVisible({ timeout: 3000 }).catch(() => false)) {
      return el.textContent();
    }
    return null;
  }
}
