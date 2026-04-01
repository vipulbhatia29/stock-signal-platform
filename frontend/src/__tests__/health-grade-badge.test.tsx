import React from "react";
import { render, screen } from "@testing-library/react";
import { HealthGradeBadge } from "@/components/health-grade-badge";

describe("HealthGradeBadge", () => {
  it("renders grade and score", () => {
    render(<HealthGradeBadge grade="A" score={9.2} />);
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("9.2/10")).toBeInTheDocument();
  });

  it("handles undefined grade without crashing", () => {
    // @ts-expect-error — testing runtime safety for undefined grade
    render(<HealthGradeBadge grade={undefined} />);
    // Should not throw — renders with default styling
  });

  it("renders without score", () => {
    render(<HealthGradeBadge grade="B+" />);
    expect(screen.getByText("B+")).toBeInTheDocument();
  });
});
