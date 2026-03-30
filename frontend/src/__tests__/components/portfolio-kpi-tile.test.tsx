import React from "react";
import { render, screen } from "@testing-library/react";
import { PortfolioKPITile } from "@/components/portfolio-kpi-tile";

test("renders label and value", () => {
  render(<PortfolioKPITile label="Total Value" value="$124,830" />);
  expect(screen.getByText("Total Value")).toBeInTheDocument();
  expect(screen.getByText("$124,830")).toBeInTheDocument();
});

test("renders subtext when provided", () => {
  render(<PortfolioKPITile label="Return" value="+12.5%" subtext="Since Jan 2025" />);
  expect(screen.getByText("Since Jan 2025")).toBeInTheDocument();
});

test("applies accent gain class", () => {
  const { container } = render(<PortfolioKPITile label="Gain" value="+5%" accent="gain" />);
  const tile = container.firstChild as HTMLElement;
  expect(tile.className).toContain("border-t-[var(--gain)]");
});
