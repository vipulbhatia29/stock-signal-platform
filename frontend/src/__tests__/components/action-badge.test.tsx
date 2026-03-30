import React from "react";
import { render, screen } from "@testing-library/react";
import { ActionBadge } from "@/components/action-badge";

describe("ActionBadge", () => {
  it("renders Buy for BUY action", () => {
    render(<ActionBadge action="BUY" />);
    expect(screen.getByText("Buy")).toBeInTheDocument();
  });

  it("renders Strong Buy for STRONG_BUY", () => {
    render(<ActionBadge action="STRONG_BUY" />);
    expect(screen.getByText("Strong Buy")).toBeInTheDocument();
  });

  it("renders Watch for WATCH action", () => {
    render(<ActionBadge action="WATCH" />);
    expect(screen.getByText("Watch")).toBeInTheDocument();
  });

  it("renders Watch for AVOID action", () => {
    render(<ActionBadge action="AVOID" />);
    expect(screen.getByText("Watch")).toBeInTheDocument();
  });

  it("renders Sell for SELL action", () => {
    render(<ActionBadge action="SELL" />);
    expect(screen.getByText("Sell")).toBeInTheDocument();
  });

  it("renders Hold for unknown action", () => {
    render(<ActionBadge action="UNKNOWN" />);
    expect(screen.getByText("Hold")).toBeInTheDocument();
  });

  it("is case-insensitive", () => {
    render(<ActionBadge action="buy" />);
    expect(screen.getByText("Buy")).toBeInTheDocument();
  });
});
