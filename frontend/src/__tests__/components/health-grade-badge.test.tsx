import React from "react";
import { render, screen } from "@testing-library/react";
import { HealthGradeBadge } from "@/components/health-grade-badge";

test("renders grade letter", () => {
  render(<HealthGradeBadge grade="A+" />);
  expect(screen.getByText("A+")).toBeInTheDocument();
});

test("renders score when provided", () => {
  render(<HealthGradeBadge grade="B" score={78} />);
  expect(screen.getByText("78/100")).toBeInTheDocument();
});

test("applies correct color for C grade (warning)", () => {
  const { container } = render(<HealthGradeBadge grade="C" />);
  const badge = container.firstChild as HTMLElement;
  expect(badge.className).toContain("text-[var(--warning)]");
});
