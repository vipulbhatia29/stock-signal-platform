import React from "react";
import { render, screen } from "@testing-library/react";
import { SignalBadge } from "@/components/signal-badge";

jest.mock("@/lib/signals", () => ({
  signalToSentiment: () => "neutral",
  SENTIMENT_CLASSES: { bullish: "text-gain", neutral: "text-neutral", bearish: "text-loss" },
  SENTIMENT_BG_CLASSES: { bullish: "bg-gain/10", neutral: "bg-neutral/10", bearish: "bg-loss/10" },
}));

test("renders BUY signal with gain styling", () => {
  const { container } = render(<SignalBadge signal="BUY" />);
  expect(screen.getByText("BUY")).toBeInTheDocument();
  expect(container.querySelector("span")?.className).toContain("text-gain");
});

test("renders WATCH signal with cyan styling", () => {
  const { container } = render(<SignalBadge signal="WATCH" />);
  expect(screen.getByText("WATCH")).toBeInTheDocument();
  expect(container.querySelector("span")?.className).toContain("text-cyan");
});

test("renders AVOID signal with loss styling", () => {
  const { container } = render(<SignalBadge signal="AVOID" />);
  expect(screen.getByText("AVOID")).toBeInTheDocument();
  expect(container.querySelector("span")?.className).toContain("text-loss");
});

test("renders GOLDEN_CROSS with custom label", () => {
  render(<SignalBadge signal="GOLDEN_CROSS" />);
  expect(screen.getByText("Golden ×")).toBeInTheDocument();
});

test("renders ABOVE_200 with custom label", () => {
  render(<SignalBadge signal="ABOVE_200" />);
  expect(screen.getByText("Above 200")).toBeInTheDocument();
});

test("renders N/A for null signal", () => {
  render(<SignalBadge signal={null} />);
  expect(screen.getByText("N/A")).toBeInTheDocument();
});

test("md size applies larger padding", () => {
  const { container } = render(<SignalBadge signal="BUY" size="md" />);
  expect(container.querySelector("span")?.className).toContain("text-xs");
});
