import React from "react";
import { render, screen } from "@testing-library/react";
import { StatusDot } from "@/components/command-center/status-dot";

test("renders green for ok status", () => {
  render(<StatusDot status="ok" />);
  const dot = screen.getByTestId("status-dot");
  expect(dot.className).toContain("bg-emerald-400");
  expect(dot.className).toContain("animate-pulse");
});

test("renders green for healthy status", () => {
  render(<StatusDot status="healthy" />);
  const dot = screen.getByTestId("status-dot");
  expect(dot.className).toContain("bg-emerald-400");
});

test("renders yellow for degraded status", () => {
  render(<StatusDot status="degraded" />);
  const dot = screen.getByTestId("status-dot");
  expect(dot.className).toContain("bg-yellow-400");
  expect(dot.className).not.toContain("animate-pulse");
});

test("renders red for down status", () => {
  render(<StatusDot status="down" />);
  const dot = screen.getByTestId("status-dot");
  expect(dot.className).toContain("bg-red-500");
});

test("renders small size variant", () => {
  render(<StatusDot status="ok" size="sm" />);
  const dot = screen.getByTestId("status-dot");
  expect(dot.className).toContain("h-2");
  expect(dot.className).toContain("w-2");
});

test("sets data-status attribute", () => {
  render(<StatusDot status="degraded" />);
  const dot = screen.getByTestId("status-dot");
  expect(dot).toHaveAttribute("data-status", "degraded");
});
