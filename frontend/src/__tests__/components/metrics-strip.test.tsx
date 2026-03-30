import React from "react";
import { render, screen } from "@testing-library/react";
import { MetricsStrip, type MetricChip } from "@/components/metrics-strip";

const METRICS: MetricChip[] = [
  { label: "RSI", value: "65", sentiment: "positive" },
  { label: "PE", value: "22.1", sentiment: "neutral" },
  { label: "Beta", value: "1.3", sentiment: "warning", primary: true },
];

test("renders all metric chips with label and value", () => {
  render(<MetricsStrip metrics={METRICS} />);
  expect(screen.getByText("RSI")).toBeInTheDocument();
  expect(screen.getByText("65")).toBeInTheDocument();
  expect(screen.getByText("PE")).toBeInTheDocument();
  expect(screen.getByText("22.1")).toBeInTheDocument();
});

test("sets data-primary attribute on primary chips", () => {
  const { container } = render(<MetricsStrip metrics={METRICS} />);
  const chips = container.querySelectorAll("[data-primary]");
  expect(chips).toHaveLength(1);
});

test("hides chips beyond maxVisible with hidden class", () => {
  const manyMetrics: MetricChip[] = [
    { label: "A", value: "1", sentiment: "positive" },
    { label: "B", value: "2", sentiment: "neutral" },
    { label: "C", value: "3", sentiment: "negative" },
  ];
  const { container } = render(
    <MetricsStrip metrics={manyMetrics} maxVisible={2} />,
  );
  const chips = container.querySelectorAll(".hidden");
  expect(chips).toHaveLength(1);
});
