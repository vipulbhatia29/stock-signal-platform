import React from "react";
import { render, screen } from "@testing-library/react";
import { ForecastHealthPanel } from "@/components/command-center/forecast-health-panel";
import type { ForecastHealthZone } from "@/types/command-center";

const MOCK_HEALTHY: ForecastHealthZone = {
  backtest_health_pct: 85.0,
  models_passing: 17,
  models_total: 20,
  sentiment_coverage_pct: 92.0,
  tickers_with_sentiment: 46,
  tickers_total: 50,
};

const MOCK_DEGRADED: ForecastHealthZone = {
  backtest_health_pct: 55.0,
  models_passing: 5,
  models_total: 9,
  sentiment_coverage_pct: 40.0,
  tickers_with_sentiment: 8,
  tickers_total: 20,
};

const MOCK_AMBER: ForecastHealthZone = {
  backtest_health_pct: 70.0,
  models_passing: 7,
  models_total: 10,
  sentiment_coverage_pct: 65.0,
  tickers_with_sentiment: 13,
  tickers_total: 20,
};

test("renders backtest and sentiment metrics with correct values", () => {
  render(<ForecastHealthPanel data={MOCK_HEALTHY} />);
  expect(screen.getByText("Forecast Health")).toBeInTheDocument();
  expect(screen.getByText("85%")).toBeInTheDocument();
  expect(screen.getByText("17/20 models")).toBeInTheDocument();
  expect(screen.getByText("92%")).toBeInTheDocument();
  expect(screen.getByText("46/50 tickers")).toBeInTheDocument();
});

test("renders green color for metrics >= 80%", () => {
  const { container } = render(<ForecastHealthPanel data={MOCK_HEALTHY} />);
  const greenElements = container.querySelectorAll(".text-emerald-400");
  expect(greenElements.length).toBeGreaterThanOrEqual(2);
});

test("renders red color for metrics < 60%", () => {
  const { container } = render(<ForecastHealthPanel data={MOCK_DEGRADED} />);
  const redElements = container.querySelectorAll(".text-red-400");
  expect(redElements.length).toBeGreaterThanOrEqual(2);
});

test("renders amber color for metrics 60-79%", () => {
  const { container } = render(<ForecastHealthPanel data={MOCK_AMBER} />);
  const amberElements = container.querySelectorAll(".text-yellow-400");
  expect(amberElements.length).toBeGreaterThanOrEqual(2);
});

test("renders unavailable state when data is null", () => {
  render(<ForecastHealthPanel data={null} />);
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
});
