import React from "react";
import { render, screen } from "@testing-library/react";
import { ScoreBadge } from "@/components/score-badge";

jest.mock("@/lib/signals", () => ({
  scoreToSentiment: (score: number | null) => {
    if (score === null) return "neutral";
    if (score >= 8) return "bullish";
    if (score >= 5) return "neutral";
    return "bearish";
  },
}));

test("renders score value", () => {
  render(<ScoreBadge score={7.5} />);
  expect(screen.getByText("7.5")).toBeInTheDocument();
});

test("renders N/A for null score", () => {
  render(<ScoreBadge score={null} />);
  expect(screen.getByText("N/A")).toBeInTheDocument();
});

test("xs size applies correct classes", () => {
  const { container } = render(<ScoreBadge score={3.2} size="xs" />);
  const badge = container.querySelector("span");
  expect(badge?.className).toContain("text-[9px]");
});

test("has tabular-nums class for number alignment", () => {
  const { container } = render(<ScoreBadge score={8.5} />);
  const badge = container.querySelector("span");
  expect(badge?.className).toContain("tabular-nums");
});
