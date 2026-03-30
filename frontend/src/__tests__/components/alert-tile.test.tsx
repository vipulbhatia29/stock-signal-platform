import React from "react";
import { render, screen } from "@testing-library/react";
import { AlertTile } from "@/components/alert-tile";

test("renders title and severity label", () => {
  render(<AlertTile title="Price dropped 10%" severity="critical" />);
  expect(screen.getByText("Price dropped 10%")).toBeInTheDocument();
  expect(screen.getByText("CRITICAL")).toBeInTheDocument();
});

test("renders ticker and timestamp when provided", () => {
  render(<AlertTile title="Dividend cut" severity="high" ticker="INTC" timestamp="2h ago" />);
  expect(screen.getByText("INTC")).toBeInTheDocument();
  expect(screen.getByText("2h ago")).toBeInTheDocument();
});

test("applies critical severity styles", () => {
  const { container } = render(<AlertTile title="Alert" severity="critical" />);
  const tile = container.firstChild as HTMLElement;
  expect(tile.className).toContain("border-l-[var(--loss)]");
  expect(tile.className).toContain("bg-loss/5");
});
