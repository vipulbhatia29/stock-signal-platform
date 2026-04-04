import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { RationaleSection } from "@/components/convergence/rationale-section";

expect.extend(toHaveNoViolations);

jest.mock("lucide-react", () => ({
  ChevronDown: (props: Record<string, unknown>) => (
    <svg data-testid="chevron-down" {...props} />
  ),
  ChevronUp: (props: Record<string, unknown>) => (
    <svg data-testid="chevron-up" {...props} />
  ),
}));

const RATIONALE =
  "4 of 6 signals are bullish. However, 90-day forecast is bearish.";

describe("RationaleSection", () => {
  it("renders nothing when rationale is null", () => {
    const { container } = render(<RationaleSection rationale={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("starts collapsed by default", () => {
    render(<RationaleSection rationale={RATIONALE} />);
    expect(screen.queryByText(RATIONALE)).not.toBeInTheDocument();
    expect(screen.getByText("Signal rationale")).toBeInTheDocument();
  });

  it("expands on click", () => {
    render(<RationaleSection rationale={RATIONALE} />);
    fireEvent.click(screen.getByText("Signal rationale"));
    expect(screen.getByText(RATIONALE)).toBeInTheDocument();
  });

  it("collapses on second click", () => {
    render(<RationaleSection rationale={RATIONALE} />);
    const button = screen.getByText("Signal rationale");
    fireEvent.click(button);
    expect(screen.getByText(RATIONALE)).toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.queryByText(RATIONALE)).not.toBeInTheDocument();
  });

  it("starts expanded when defaultOpen is true", () => {
    render(<RationaleSection rationale={RATIONALE} defaultOpen />);
    expect(screen.getByText(RATIONALE)).toBeInTheDocument();
  });

  it("has aria-expanded attribute", () => {
    render(<RationaleSection rationale={RATIONALE} />);
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("passes axe a11y checks when collapsed", async () => {
    const { container } = render(<RationaleSection rationale={RATIONALE} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("passes axe a11y checks when expanded", async () => {
    const { container } = render(
      <RationaleSection rationale={RATIONALE} defaultOpen />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
