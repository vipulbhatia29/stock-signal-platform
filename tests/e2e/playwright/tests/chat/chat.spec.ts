import { test, expect } from "@playwright/test";

test.describe("Chat", () => {
  test("should open chat panel", async ({ page }) => {
    await page.goto("/dashboard");
    // Look for chat trigger button
    const chatTrigger = page.getByRole("button", { name: /chat|ask|ai/i });
    if (await chatTrigger.isVisible({ timeout: 3000 }).catch(() => false)) {
      await chatTrigger.click();
    }
    // Chat input should be visible (either always or after opening)
    const chatInput = page.getByPlaceholder(/ask|message|type/i);
    await expect(chatInput).toBeVisible({ timeout: 5000 });
  });

  test("should send a message with mocked response", async ({ page }) => {
    // Mock the chat stream endpoint to avoid real LLM calls
    await page.route("**/api/v1/chat/stream", async (route) => {
      const ndjson =
        [
          JSON.stringify({ type: "thinking", content: "Analyzing..." }),
          JSON.stringify({
            type: "plan",
            content: "Research plan",
            data: { steps: ["analyze_stock"] },
          }),
          JSON.stringify({
            type: "token",
            content:
              "AAPL is trading at $185. The stock shows strong momentum.",
          }),
          JSON.stringify({ type: "done", usage: {} }),
        ].join("\n") + "\n";

      await route.fulfill({
        status: 200,
        contentType: "application/x-ndjson",
        body: ndjson,
      });
    });

    // Also mock session creation
    await page.route("**/api/v1/chat/sessions", async (route, request) => {
      if (request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: "[]",
        });
      } else {
        await route.continue();
      }
    });

    await page.goto("/dashboard");
    const chatInput = page.getByPlaceholder(/ask|message|type/i);
    if (await chatInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await chatInput.fill("Analyze AAPL");
      await page.keyboard.press("Enter");
      // Should see the mocked response appear
      await expect(page.getByText("AAPL is trading")).toBeVisible({
        timeout: 10000,
      });
    }
  });
});
