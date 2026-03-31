import React from "react";
import { render, screen } from "@testing-library/react";
import { MetricCard } from "@/components/command-center/metric-card";

test("renders label and value", () => {
  render(<MetricCard label="RPS" value="42.5" />);
  expect(screen.getByText("RPS")).toBeInTheDocument();
  expect(screen.getByText("42.5")).toBeInTheDocument();
});

test("renders subtitle when provided", () => {
  render(<MetricCard label="Cost" value="$1.23" subtitle="+10% vs yesterday" />);
  expect(screen.getByText("+10% vs yesterday")).toBeInTheDocument();
});

test("applies status color for error", () => {
  render(<MetricCard label="Errors" value="15%" status="error" />);
  const valueEl = screen.getByText("15%");
  expect(valueEl.className).toContain("text-red-500");
});

test("applies status color for ok", () => {
  render(<MetricCard label="Health" value="100%" status="ok" />);
  const valueEl = screen.getByText("100%");
  expect(valueEl.className).toContain("text-emerald-400");
});

test("renders numeric value", () => {
  render(<MetricCard label="Count" value={1234} />);
  expect(screen.getByText("1234")).toBeInTheDocument();
});
