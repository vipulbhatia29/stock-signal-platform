import React from "react";
import { render, screen } from "@testing-library/react";
import { BLForecastCard } from "@/components/portfolio/bl-forecast-card";
import type { BLSummary } from "@/types/api";

jest.mock("lucide-react", () => ({
  TrendingUp: (props: Record<string, unknown>) => (
    <svg data-testid="icon-up" {...props} />
  ),
  TrendingDown: (props: Record<string, unknown>) => (
    <svg data-testid="icon-down" {...props} />
  ),
  Minus: (props: Record<string, unknown>) => (
    <svg data-testid="icon-neutral" {...props} />
  ),
}));

const POSITIVE_BL: BLSummary = {
  portfolio_expected_return: 0.125,
  risk_free_rate: 0.05,
  per_ticker: [
    { ticker: "AAPL", expected_return: 0.18, view_confidence: 0.8 },
    { ticker: "MSFT", expected_return: 0.15, view_confidence: 0.7 },
  ],
};

const NEGATIVE_BL: BLSummary = {
  portfolio_expected_return: -0.05,
  risk_free_rate: 0.05,
  per_ticker: [
    { ticker: "AAPL", expected_return: -0.08, view_confidence: 0.6 },
  ],
};

describe("BLForecastCard", () => {
  it("renders nothing when data is undefined", () => {
    const { container } = render(
      <BLForecastCard data={undefined} isLoading={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders loading skeleton", () => {
    const { container } = render(
      <BLForecastCard data={undefined} isLoading={true} />,
    );
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows positive return with gain color", () => {
    const { container } = render(
      <BLForecastCard data={POSITIVE_BL} isLoading={false} />,
    );
    expect(screen.getByText("+12.5%")).toBeInTheDocument();
    expect(container.querySelector(".text-gain")).toBeInTheDocument();
    expect(screen.getByTestId("icon-up")).toBeInTheDocument();
  });

  it("shows negative return with loss color", () => {
    const { container } = render(
      <BLForecastCard data={NEGATIVE_BL} isLoading={false} />,
    );
    expect(screen.getByText("-5.0%")).toBeInTheDocument();
    expect(container.querySelector(".text-loss")).toBeInTheDocument();
  });

  it("shows per-ticker breakdown", () => {
    render(<BLForecastCard data={POSITIVE_BL} isLoading={false} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("+18.0%")).toBeInTheDocument();
  });
});
