import React from "react";
import { render, screen } from "@testing-library/react";
import { CVaRCard } from "@/components/portfolio/cvar-card";
import type { CVaRSummary } from "@/types/api";

jest.mock("lucide-react", () => ({
  ShieldAlert: (props: Record<string, unknown>) => (
    <svg data-testid="shield-icon" {...props} />
  ),
}));

const MOCK_CVAR: CVaRSummary = {
  cvar_95_pct: -12.5,
  cvar_99_pct: -18.3,
  var_95_pct: -8.2,
  var_99_pct: -14.1,
  description_95: "In a bad month (1-in-20): -12.5%",
  description_99: "In a very bad month (1-in-100): -18.3%",
};

describe("CVaRCard", () => {
  it("renders nothing when data is undefined", () => {
    const { container } = render(
      <CVaRCard data={undefined} isLoading={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders loading skeleton", () => {
    const { container } = render(
      <CVaRCard data={undefined} isLoading={true} />,
    );
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows both risk scenarios", () => {
    render(<CVaRCard data={MOCK_CVAR} isLoading={false} />);
    expect(screen.getByText("In a bad month")).toBeInTheDocument();
    expect(screen.getByText("In a very bad month")).toBeInTheDocument();
    expect(screen.getByText("-12.5%")).toBeInTheDocument();
    expect(screen.getByText("-18.3%")).toBeInTheDocument();
  });

  it("uses warning color for 95% and loss color for 99%", () => {
    const { container } = render(
      <CVaRCard data={MOCK_CVAR} isLoading={false} />,
    );
    expect(container.querySelector(".text-warning")).toBeInTheDocument();
    expect(container.querySelector(".text-loss")).toBeInTheDocument();
  });

  it("renders shield icon", () => {
    render(<CVaRCard data={MOCK_CVAR} isLoading={false} />);
    expect(screen.getByTestId("shield-icon")).toBeInTheDocument();
  });
});
