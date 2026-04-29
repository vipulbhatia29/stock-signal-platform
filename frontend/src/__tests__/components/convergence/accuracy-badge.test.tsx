import React from "react";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { AccuracyBadge } from "@/components/convergence/accuracy-badge";
import type { ModelAccuracy } from "@/types/api";

expect.extend(toHaveNoViolations);

const highAccuracy: ModelAccuracy = {
  direction_hit_rate: 0.75,
  avg_error_pct: 3.2,
  ci_containment_rate: 0.82,
  evaluated_count: 50,
};

const mediumAccuracy: ModelAccuracy = {
  direction_hit_rate: 0.60,
  avg_error_pct: 8.1,
  ci_containment_rate: 0.78,
  evaluated_count: 30,
};

const lowAccuracy: ModelAccuracy = {
  direction_hit_rate: 0.48,
  avg_error_pct: 15.0,
  ci_containment_rate: 0.65,
  evaluated_count: 20,
};

describe("AccuracyBadge", () => {
  it("renders nothing when accuracy is null", () => {
    const { container } = render(<AccuracyBadge accuracy={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows High for direction_hit_rate >= 0.70", () => {
    render(<AccuracyBadge accuracy={highAccuracy} />);
    expect(screen.getByText(/High/)).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("shows Medium for direction_hit_rate 0.55-0.69", () => {
    render(<AccuracyBadge accuracy={mediumAccuracy} />);
    expect(screen.getByText(/Medium/)).toBeInTheDocument();
  });

  it("shows Low for direction_hit_rate < 0.55", () => {
    render(<AccuracyBadge accuracy={lowAccuracy} />);
    expect(screen.getByText(/Low/)).toBeInTheDocument();
  });

  it("uses gain color for high accuracy", () => {
    const { container } = render(<AccuracyBadge accuracy={highAccuracy} />);
    expect(container.querySelector(".text-gain")).toBeInTheDocument();
  });

  it("uses warning color for medium accuracy", () => {
    const { container } = render(<AccuracyBadge accuracy={mediumAccuracy} />);
    expect(container.querySelector(".text-warning")).toBeInTheDocument();
  });

  it("uses loss color for low accuracy", () => {
    const { container } = render(<AccuracyBadge accuracy={lowAccuracy} />);
    expect(container.querySelector(".text-loss")).toBeInTheDocument();
  });

  it("has aria-label with accuracy info", () => {
    render(<AccuracyBadge accuracy={mediumAccuracy} />);
    const badge = screen.getByLabelText(/Forecast accuracy: Medium/);
    expect(badge).toBeInTheDocument();
  });

  it("passes axe a11y checks for span variant", async () => {
    const { container } = render(<AccuracyBadge accuracy={highAccuracy} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("passes axe a11y checks for button variant", async () => {
    const { container } = render(
      <AccuracyBadge accuracy={highAccuracy} onClick={() => undefined} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
