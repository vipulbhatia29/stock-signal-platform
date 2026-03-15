import React from "react";
import { render, screen } from "@testing-library/react";
import { PortfolioDrawer } from "@/components/portfolio-drawer";

// Mock lucide-react
jest.mock("lucide-react", () => ({
  XIcon: () => <svg data-testid="x-icon" />,
}));

// Mock the hooks used inside PortfolioDrawer
jest.mock("@/hooks/use-stocks", () => ({
  usePortfolioSummary: () => ({ data: null }),
  usePortfolioHistory: () => ({ data: [] }),
}));

// Mock PortfolioValueChart
jest.mock("@/components/portfolio-value-chart", () => ({
  PortfolioValueChart: () => <div data-testid="portfolio-value-chart" />,
}));

// Mock formatCurrency
jest.mock("@/lib/format", () => ({
  formatCurrency: (v: number) => `$${v.toFixed(2)}`,
}));

test("drawer has height 0 when closed", () => {
  const { container } = render(
    <PortfolioDrawer isOpen={false} onClose={jest.fn()} chatIsOpen={false} />
  );
  // Find the fixed drawer (not the backdrop) by checking for height:0
  const allDivs = container.querySelectorAll("div[style]");
  const drawerDiv = Array.from(allDivs).find(
    (el) => (el as HTMLElement).style.height === "0px" || (el as HTMLElement).style.height === "0"
  );
  expect(drawerDiv).toBeTruthy();
});

test("renders close button when open", () => {
  render(
    <PortfolioDrawer isOpen={true} onClose={jest.fn()} chatIsOpen={false} />
  );
  expect(screen.getByLabelText("Close portfolio chart")).toBeInTheDocument();
});
