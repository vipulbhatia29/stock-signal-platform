import React from "react";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { TrafficLightRow, TrafficLightRowSkeleton } from "@/components/convergence/traffic-light-row";
import type { SignalDirectionDetail } from "@/types/api";

expect.extend(toHaveNoViolations);

const MOCK_SIGNALS: SignalDirectionDetail[] = [
  { signal: "rsi", direction: "bullish", value: 35.0 },
  { signal: "macd", direction: "bullish", value: 0.05 },
  { signal: "sma", direction: "bearish", value: 95.0 },
  { signal: "piotroski", direction: "neutral", value: 5 },
  { signal: "forecast", direction: "bullish", value: 0.08 },
  { signal: "news", direction: "neutral", value: 0.1 },
];

describe("TrafficLightRow", () => {
  it("renders 6 signal indicators", () => {
    render(<TrafficLightRow signals={MOCK_SIGNALS} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(6);
  });

  it("has correct aria-label for each signal", () => {
    render(<TrafficLightRow signals={MOCK_SIGNALS} />);
    expect(
      screen.getByLabelText("RSI: Bullish"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("SMA: Bearish"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("F-Score: Neutral"),
    ).toBeInTheDocument();
  });

  it("has role=list on container", () => {
    render(<TrafficLightRow signals={MOCK_SIGNALS} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
  });

  it("renders bullish circles with gain color", () => {
    const { container } = render(
      <TrafficLightRow signals={MOCK_SIGNALS} />,
    );
    const circles = container.querySelectorAll(".bg-gain");
    // 3 bullish signals: rsi, macd, forecast
    expect(circles.length).toBe(3);
  });

  it("renders bearish circles with loss color", () => {
    const { container } = render(
      <TrafficLightRow signals={MOCK_SIGNALS} />,
    );
    const circles = container.querySelectorAll(".bg-loss");
    expect(circles.length).toBe(1); // sma
  });

  it("passes axe a11y checks", async () => {
    const { container } = render(
      <TrafficLightRow signals={MOCK_SIGNALS} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("TrafficLightRowSkeleton", () => {
  it("renders 6 skeleton placeholders", () => {
    /** Skeleton shows at least 6 animated pulse placeholders. */
    const { container } = render(<TrafficLightRowSkeleton />);
    const pulses = container.querySelectorAll(".animate-pulse");
    expect(pulses.length).toBeGreaterThanOrEqual(6);
  });
});

// ---------------------------------------------------------------------------
// Error / empty-state rendering
// ---------------------------------------------------------------------------

describe("TrafficLightRow — error and empty states", () => {
  it("renders empty list when signals array is empty", () => {
    /** Empty signals array should render an accessible list with no items. */
    render(<TrafficLightRow signals={[]} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("renders partial signal list without crashing when fewer than 6 signals", () => {
    /** Partial signal data (e.g. API partially populated) renders what is available. */
    const partialSignals: SignalDirectionDetail[] = [
      { signal: "rsi", direction: "bullish", value: 35.0 },
      { signal: "macd", direction: "bearish", value: -0.03 },
    ];
    render(<TrafficLightRow signals={partialSignals} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
  });

  it("handles neutral direction for all signals without any colored circles", () => {
    /** All-neutral signals produce no gain/loss colored circles. */
    const neutralSignals: SignalDirectionDetail[] = MOCK_SIGNALS.map((s) => ({
      ...s,
      direction: "neutral" as const,
    }));
    const { container } = render(<TrafficLightRow signals={neutralSignals} />);
    expect(container.querySelectorAll(".bg-gain")).toHaveLength(0);
    expect(container.querySelectorAll(".bg-loss")).toHaveLength(0);
  });
});
