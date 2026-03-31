import React from "react";
import { render, screen } from "@testing-library/react";
import { GaugeBar } from "@/components/command-center/gauge-bar";

test("renders fill at correct width", () => {
  const { container } = render(<GaugeBar value={50} max={100} />);
  const fill = container.querySelector("[style]");
  expect(fill).toHaveStyle({ width: "50%" });
});

test("renders cyan color when below warn threshold", () => {
  const { container } = render(<GaugeBar value={30} />);
  const fill = container.querySelector(".bg-cyan");
  expect(fill).toBeTruthy();
});

test("renders yellow when between warn and critical", () => {
  const { container } = render(
    <GaugeBar value={70} thresholds={{ warn: 60, critical: 85 }} />
  );
  const fill = container.querySelector(".bg-yellow-400");
  expect(fill).toBeTruthy();
});

test("renders red when above critical threshold", () => {
  const { container } = render(
    <GaugeBar value={90} thresholds={{ warn: 60, critical: 85 }} />
  );
  const fill = container.querySelector(".bg-red-500");
  expect(fill).toBeTruthy();
});

test("renders label when provided", () => {
  render(<GaugeBar value={42} label="Memory Usage" />);
  expect(screen.getByText("Memory Usage")).toBeInTheDocument();
  expect(screen.getByText("42%")).toBeInTheDocument();
});

test("clamps value to 100%", () => {
  const { container } = render(<GaugeBar value={150} max={100} />);
  const fill = container.querySelector("[style]");
  expect(fill).toHaveStyle({ width: "100%" });
});
