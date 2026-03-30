import React from "react";
import { render, screen } from "@testing-library/react";
import { ScoreRing } from "@/components/score-ring";

test("renders the score with one decimal", () => {
  render(<ScoreRing score={7.5} />);
  expect(screen.getByText("7.5")).toBeInTheDocument();
});

test("applies buy variant for score >= 8", () => {
  const { container } = render(<ScoreRing score={8.2} />);
  const el = container.firstChild as HTMLElement;
  expect(el.className).toContain("border-gain");
});

test("applies watch variant for score >= 5 and < 8", () => {
  const { container } = render(<ScoreRing score={6.0} />);
  const el = container.firstChild as HTMLElement;
  expect(el.className).toContain("border-warning");
});

test("applies sell variant for score < 5", () => {
  const { container } = render(<ScoreRing score={3.1} />);
  const el = container.firstChild as HTMLElement;
  expect(el.className).toContain("border-loss");
});

test("has aria-label with score and optional label", () => {
  render(<ScoreRing score={9.0} label="BUY" />);
  expect(
    screen.getByLabelText("Composite score 9 out of 10, BUY"),
  ).toBeInTheDocument();
});
