import React from "react";
import { render, screen } from "@testing-library/react";
import { ChangeIndicator } from "@/components/change-indicator";

jest.mock("lucide-react", () => ({
  TrendingUpIcon: (props: Record<string, unknown>) => <svg data-testid="icon-up" {...props} />,
  TrendingDownIcon: (props: Record<string, unknown>) => <svg data-testid="icon-down" {...props} />,
  MinusIcon: (props: Record<string, unknown>) => <svg data-testid="icon-neutral" {...props} />,
}));

jest.mock("@/lib/format", () => ({
  formatPercent: (v: number) => `${Math.abs(v).toFixed(1)}%`,
  formatCurrency: (v: number) => `$${Math.abs(v).toFixed(2)}`,
}));

test("renders positive change with gain color", () => {
  const { container } = render(<ChangeIndicator value={5.2} />);
  expect(container.querySelector("span")?.className).toContain("text-gain");
  expect(screen.getByTestId("icon-up")).toBeInTheDocument();
});

test("renders negative change with loss color", () => {
  const { container } = render(<ChangeIndicator value={-3.1} />);
  expect(container.querySelector("span")?.className).toContain("text-loss");
});

test("renders null as dash", () => {
  render(<ChangeIndicator value={null} />);
  expect(screen.getByText("—")).toBeInTheDocument();
});

test("prefix prop prepends text", () => {
  const { container } = render(<ChangeIndicator value={10} format="currency" prefix="$" showIcon={false} />);
  expect(container.textContent).toContain("$");
});

test("showIcon=false hides the icon", () => {
  render(<ChangeIndicator value={5} showIcon={false} />);
  expect(screen.queryByTestId("icon-up")).not.toBeInTheDocument();
});

test("has tabular-nums for alignment", () => {
  const { container } = render(<ChangeIndicator value={1.5} />);
  expect(container.querySelector("span")?.className).toContain("tabular-nums");
});
