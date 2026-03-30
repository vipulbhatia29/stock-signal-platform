import React from "react";
import { render, screen } from "@testing-library/react";
import { SectorPerformanceBars } from "@/components/sector-performance-bars";

const SECTORS = [
  { sector: "Technology", changePct: 2.34 },
  { sector: "Energy", changePct: -1.56 },
  { sector: "Healthcare", changePct: 0.45 },
];

test("renders sector names", () => {
  render(<SectorPerformanceBars sectors={SECTORS} />);
  expect(screen.getByText("Technology")).toBeInTheDocument();
  expect(screen.getByText("Energy")).toBeInTheDocument();
  expect(screen.getByText("Healthcare")).toBeInTheDocument();
});

test("renders formatted percentages with sign", () => {
  render(<SectorPerformanceBars sectors={SECTORS} />);
  expect(screen.getByText("+2.34%")).toBeInTheDocument();
  expect(screen.getByText("-1.56%")).toBeInTheDocument();
});

test("provides aria-labels with sector and percentage", () => {
  render(<SectorPerformanceBars sectors={SECTORS} />);
  expect(screen.getByLabelText("Technology: +2.34%")).toBeInTheDocument();
  expect(screen.getByLabelText("Energy: -1.56%")).toBeInTheDocument();
});
