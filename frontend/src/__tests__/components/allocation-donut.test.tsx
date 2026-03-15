import React from "react";
import { render, screen } from "@testing-library/react";
import { AllocationDonut, buildGradient } from "@/components/allocation-donut";

test("buildGradient produces correct conic-gradient stops", () => {
  const result = buildGradient([
    { sector: "Tech", pct: 60, color: "#38bdf8" },
    { sector: "Finance", pct: 40, color: "#fbbf24" },
  ]);
  expect(result).toContain("#38bdf8 0.0% 60.0%");
  expect(result).toContain("#fbbf24 60.0% 100.0%");
});

test("renders 'No positions' when allocations is empty", () => {
  render(<AllocationDonut allocations={[]} />);
  expect(screen.getByText("No positions")).toBeInTheDocument();
});

test("renders sector legend items", () => {
  render(
    <AllocationDonut
      allocations={[
        { sector: "Tech", pct: 60, color: "#38bdf8" },
        { sector: "Finance", pct: 40, color: "#fbbf24" },
      ]}
      stockCount={5}
    />
  );
  expect(screen.getByText("Tech")).toBeInTheDocument();
  expect(screen.getByText("Finance")).toBeInTheDocument();
});
