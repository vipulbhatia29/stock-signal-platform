import React from "react";
import { render, screen } from "@testing-library/react";
import { HealthGradeBadge } from "@/components/health-grade-badge";

test("renders grade letter", () => {
  render(<HealthGradeBadge grade="A+" />);
  expect(screen.getByText("A+")).toBeInTheDocument();
});

test("renders score when provided", () => {
  render(<HealthGradeBadge grade="B" score={7.8} />);
  expect(screen.getByText("7.8/10")).toBeInTheDocument();
});

test("applies correct color for C grade (warning)", () => {
  const { container } = render(<HealthGradeBadge grade="C" />);
  const badge = container.firstChild as HTMLElement;
  expect(badge.className).toContain("text-[var(--warning)]");
});

test("handles undefined grade without crashing", () => {
  // @ts-expect-error — testing runtime safety for undefined grade
  render(<HealthGradeBadge grade={undefined} />);
  // Should not throw — renders with default styling
});

test("renders without score", () => {
  render(<HealthGradeBadge grade="B+" />);
  expect(screen.getByText("B+")).toBeInTheDocument();
});
