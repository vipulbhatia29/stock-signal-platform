import React from "react";
import { render, screen } from "@testing-library/react";
import { ConvergenceSummary } from "@/components/portfolio/convergence-summary";
import type { PortfolioConvergenceResponse } from "@/types/api";

const MOCK_DATA: PortfolioConvergenceResponse = {
  portfolio_id: "portfolio-1",
  date: "2026-04-03",
  positions: [
    {
      ticker: "AAPL",
      weight: 0.6,
      convergence_label: "strong_bull",
      signals_aligned: 5,
      divergence: {
        is_divergent: false,
        forecast_direction: null,
        technical_majority: null,
        historical_hit_rate: null,
        sample_count: null,
      },
    },
    {
      ticker: "MSFT",
      weight: 0.4,
      convergence_label: "weak_bear",
      signals_aligned: 3,
      divergence: {
        is_divergent: true,
        forecast_direction: "bearish",
        technical_majority: "bullish",
        historical_hit_rate: 0.55,
        sample_count: 12,
      },
    },
  ],
  bullish_pct: 0.6,
  bearish_pct: 0.4,
  mixed_pct: 0.0,
  divergent_positions: ["MSFT"],
};

describe("ConvergenceSummary", () => {
  it("renders nothing when data is undefined", () => {
    const { container } = render(
      <ConvergenceSummary data={undefined} isLoading={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders loading skeleton", () => {
    const { container } = render(
      <ConvergenceSummary data={undefined} isLoading={true} />,
    );
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows bullish and bearish percentages", () => {
    render(<ConvergenceSummary data={MOCK_DATA} isLoading={false} />);
    expect(screen.getByText(/Bullish 60%/)).toBeInTheDocument();
    expect(screen.getByText(/Bearish 40%/)).toBeInTheDocument();
  });

  it("shows divergent positions", () => {
    render(<ConvergenceSummary data={MOCK_DATA} isLoading={false} />);
    expect(screen.getByText(/MSFT/)).toBeInTheDocument();
    expect(screen.getByText(/Divergent/)).toBeInTheDocument();
  });

  it("has aria-label on stacked bar", () => {
    render(<ConvergenceSummary data={MOCK_DATA} isLoading={false} />);
    const bar = screen.getByRole("img");
    expect(bar).toHaveAttribute(
      "aria-label",
      "60% bullish, 40% bearish, 0% mixed",
    );
  });

  it("renders stacked bar segments", () => {
    const { container } = render(
      <ConvergenceSummary data={MOCK_DATA} isLoading={false} />,
    );
    expect(container.querySelector(".bg-gain")).toBeInTheDocument();
    expect(container.querySelector(".bg-loss")).toBeInTheDocument();
  });
});
