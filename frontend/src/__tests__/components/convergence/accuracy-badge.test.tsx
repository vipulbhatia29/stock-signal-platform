import React from "react";
import { render, screen } from "@testing-library/react";
import { AccuracyBadge } from "@/components/convergence/accuracy-badge";

describe("AccuracyBadge", () => {
  it("renders nothing when mape is null", () => {
    const { container } = render(<AccuracyBadge mape={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows High accuracy for MAPE <= 5", () => {
    render(<AccuracyBadge mape={3.2} />);
    expect(screen.getByText(/High accuracy/)).toBeInTheDocument();
    expect(screen.getByText("3.2%")).toBeInTheDocument();
  });

  it("shows Medium accuracy for MAPE 5-15", () => {
    render(<AccuracyBadge mape={10.0} />);
    expect(screen.getByText(/Medium accuracy/)).toBeInTheDocument();
  });

  it("shows Low accuracy for MAPE > 15", () => {
    render(<AccuracyBadge mape={22.5} />);
    expect(screen.getByText(/Low accuracy/)).toBeInTheDocument();
  });

  it("uses gain color for high accuracy", () => {
    const { container } = render(<AccuracyBadge mape={3.0} />);
    expect(container.querySelector(".text-gain")).toBeInTheDocument();
  });

  it("uses warning color for medium accuracy", () => {
    const { container } = render(<AccuracyBadge mape={10.0} />);
    expect(container.querySelector(".text-warning")).toBeInTheDocument();
  });

  it("uses loss color for low accuracy", () => {
    const { container } = render(<AccuracyBadge mape={20.0} />);
    expect(container.querySelector(".text-loss")).toBeInTheDocument();
  });

  it("has aria-label with accuracy info", () => {
    render(<AccuracyBadge mape={8.5} />);
    const badge = screen.getByLabelText(/Forecast accuracy: Medium/);
    expect(badge).toBeInTheDocument();
  });
});
