import React from "react";
import { render, screen } from "@testing-library/react";
import { TrafficLightRow, TrafficLightRowSkeleton } from "@/components/convergence/traffic-light-row";
import type { SignalDirectionDetail } from "@/types/api";

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
});

describe("TrafficLightRowSkeleton", () => {
  it("renders 6 skeleton placeholders", () => {
    const { container } = render(<TrafficLightRowSkeleton />);
    const pulses = container.querySelectorAll(".animate-pulse");
    expect(pulses.length).toBeGreaterThanOrEqual(6);
  });
});
