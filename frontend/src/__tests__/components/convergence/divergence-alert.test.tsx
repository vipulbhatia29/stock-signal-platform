import React from "react";
import { render, screen } from "@testing-library/react";
import { DivergenceAlert } from "@/components/convergence/divergence-alert";
import type { DivergenceAlert as DivergenceAlertType } from "@/types/api";

jest.mock("lucide-react", () => ({
  AlertTriangle: (props: Record<string, unknown>) => (
    <svg data-testid="alert-icon" {...props} />
  ),
}));

const DIVERGENT: DivergenceAlertType = {
  is_divergent: true,
  forecast_direction: "bearish",
  technical_majority: "bullish",
  historical_hit_rate: 0.61,
  sample_count: 23,
};

const NOT_DIVERGENT: DivergenceAlertType = {
  is_divergent: false,
  forecast_direction: null,
  technical_majority: null,
  historical_hit_rate: null,
  sample_count: null,
};

describe("DivergenceAlert", () => {
  it("renders nothing when not divergent", () => {
    const { container } = render(
      <DivergenceAlert divergence={NOT_DIVERGENT} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders alert when divergent", () => {
    render(<DivergenceAlert divergence={DIVERGENT} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Signal divergence/)).toBeInTheDocument();
  });

  it("shows forecast and technical directions", () => {
    render(<DivergenceAlert divergence={DIVERGENT} />);
    expect(screen.getByText("bearish")).toBeInTheDocument();
    expect(screen.getByText("bullish")).toBeInTheDocument();
  });

  it("shows historical hit rate when available", () => {
    render(<DivergenceAlert divergence={DIVERGENT} />);
    expect(screen.getByText(/61%/)).toBeInTheDocument();
    expect(screen.getByText(/23 cases/)).toBeInTheDocument();
  });

  it("hides hit rate when not available", () => {
    const noHitRate: DivergenceAlertType = {
      ...DIVERGENT,
      historical_hit_rate: null,
      sample_count: null,
    };
    render(<DivergenceAlert divergence={noHitRate} />);
    expect(screen.queryByText(/cases/)).not.toBeInTheDocument();
  });

  it("has aria-live=polite for accessibility", () => {
    render(<DivergenceAlert divergence={DIVERGENT} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveAttribute("aria-live", "polite");
  });

  it("renders alert icon", () => {
    render(<DivergenceAlert divergence={DIVERGENT} />);
    expect(screen.getByTestId("alert-icon")).toBeInTheDocument();
  });
});
