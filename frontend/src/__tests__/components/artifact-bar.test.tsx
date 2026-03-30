import { render, screen } from "@testing-library/react";
import { ArtifactBar, shouldPin } from "@/components/chat/artifact-bar";

describe("shouldPin", () => {
  it("returns true for analyze_stock", () => expect(shouldPin("analyze_stock")).toBe(true));
  it("returns true for screen_stocks", () => expect(shouldPin("screen_stocks")).toBe(true));
  it("returns false for web_search", () => expect(shouldPin("web_search")).toBe(false));
  it("returns false for geopolitical", () => expect(shouldPin("geopolitical")).toBe(false));
  it("returns true for get_recommendations", () => expect(shouldPin("get_recommendations")).toBe(true));
});

test("renders artifact with dismiss button", () => {
  const onDismiss = jest.fn();
  render(
    <ArtifactBar
      artifact={{ tool: "analyze_stock", params: { ticker: "AAPL" }, data: { score: 7.2 } }}
      onDismiss={onDismiss}
    />
  );
  expect(screen.getByText(/analyze_stock/)).toBeInTheDocument();
});
