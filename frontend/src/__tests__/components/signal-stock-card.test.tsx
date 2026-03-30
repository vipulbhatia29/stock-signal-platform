import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SignalStockCard } from "@/components/signal-stock-card";
import type { MetricChip } from "@/components/metrics-strip";

const METRICS: MetricChip[] = [
  { label: "RSI", value: "72", sentiment: "positive" },
];

test("renders ticker symbol", () => {
  render(
    <SignalStockCard
      ticker="AAPL"
      compositeScore={8.5}
      action="BUY"
      metrics={METRICS}
    />,
  );
  expect(screen.getByText("AAPL")).toBeInTheDocument();
});

test("renders company name when provided", () => {
  render(
    <SignalStockCard
      ticker="AAPL"
      name="Apple Inc."
      compositeScore={8.5}
      action="BUY"
      metrics={METRICS}
    />,
  );
  expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
});

test("renders score ring with composite score", () => {
  render(
    <SignalStockCard
      ticker="AAPL"
      compositeScore={8.5}
      action="BUY"
      metrics={METRICS}
    />,
  );
  expect(screen.getByText("8.5")).toBeInTheDocument();
});

test("renders action badge", () => {
  render(
    <SignalStockCard
      ticker="AAPL"
      compositeScore={8.5}
      action="BUY"
      metrics={METRICS}
    />,
  );
  expect(screen.getByText("Buy")).toBeInTheDocument();
});

test("renders reason text when provided", () => {
  render(
    <SignalStockCard
      ticker="AAPL"
      compositeScore={8.5}
      action="BUY"
      metrics={METRICS}
      reason="Strong momentum and fundamentals"
    />,
  );
  expect(
    screen.getByText("Strong momentum and fundamentals"),
  ).toBeInTheDocument();
});

test("applies buy card variant for score >= 8", () => {
  const { container } = render(
    <SignalStockCard
      ticker="AAPL"
      compositeScore={9.0}
      action="BUY"
      metrics={METRICS}
    />,
  );
  const card = container.firstChild as HTMLElement;
  expect(card.className).toContain("border-gain");
});

test("renders as button and handles click when onClick provided", () => {
  const handleClick = jest.fn();
  render(
    <SignalStockCard
      ticker="AAPL"
      compositeScore={8.5}
      action="BUY"
      metrics={METRICS}
      onClick={handleClick}
    />,
  );
  const button = screen.getByRole("button");
  fireEvent.click(button);
  expect(handleClick).toHaveBeenCalledTimes(1);
});
