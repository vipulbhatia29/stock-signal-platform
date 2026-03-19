import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToolCard } from "@/components/chat/tool-card";

test("shows spinner when status is running", () => {
  render(
    <ToolCard tool="analyze_stock" params={{ ticker: "AAPL" }} status="running" />
  );
  expect(screen.getByText("analyze_stock")).toBeInTheDocument();
  expect(screen.getByText(/AAPL/)).toBeInTheDocument();
});

test("shows result summary when completed", () => {
  render(
    <ToolCard
      tool="analyze_stock"
      params={{ ticker: "AAPL" }}
      status="completed"
      result={{ composite_score: 7.2, rsi_value: 55 }}
    />
  );
  expect(screen.getByText(/7\.2/)).toBeInTheDocument();
});

test("shows error styling when status is error", () => {
  render(
    <ToolCard
      tool="analyze_stock"
      params={{ ticker: "AAPL" }}
      status="error"
      result={{ error: "API timeout" }}
    />
  );
  expect(screen.getByText(/API timeout/)).toBeInTheDocument();
});

test("expands to show full result on click", async () => {
  render(
    <ToolCard
      tool="analyze_stock"
      params={{ ticker: "AAPL" }}
      status="completed"
      result={{ composite_score: 7.2, rsi_value: 55, macd_signal: "BULLISH" }}
    />
  );
  await userEvent.click(screen.getByText(/Show full result/));
  expect(screen.getByText(/macd_signal/)).toBeInTheDocument();
});
