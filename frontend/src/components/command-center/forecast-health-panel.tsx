"use client";

import type { ForecastHealthZone } from "@/types/command-center";

interface ForecastHealthPanelProps {
  data: ForecastHealthZone | null;
}

function healthColor(pct: number): string {
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 60) return "text-yellow-400";
  return "text-red-400";
}

export function ForecastHealthPanel({ data }: ForecastHealthPanelProps) {
  if (!data) {
    return (
      <div className="rounded-xl bg-card border border-border p-5">
        <h3 className="text-sm font-medium text-subtle mb-3">Forecast Health</h3>
        <p className="text-xs text-subtle">Unavailable</p>
      </div>
    );
  }

  const backtestPct = Math.round(data.backtest_health_pct);
  const sentimentPct = Math.round(data.sentiment_coverage_pct);

  return (
    <div data-testid="forecast-health-panel" className="rounded-xl bg-card border border-border p-5">
      <h3 className="text-sm font-medium mb-4">Forecast Health</h3>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-subtle mb-1">Backtest Accuracy</p>
          <p className={`text-2xl font-semibold font-mono ${healthColor(data.backtest_health_pct)}`}>
            {backtestPct}%
          </p>
          <p className="text-xs text-subtle mt-1">
            {data.models_passing}/{data.models_total} models
          </p>
        </div>
        <div>
          <p className="text-xs text-subtle mb-1">Sentiment Coverage</p>
          <p className={`text-2xl font-semibold font-mono ${healthColor(data.sentiment_coverage_pct)}`}>
            {sentimentPct}%
          </p>
          <p className="text-xs text-subtle mt-1">
            {data.tickers_with_sentiment}/{data.tickers_total} tickers
          </p>
        </div>
      </div>
    </div>
  );
}
