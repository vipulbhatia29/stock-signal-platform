"use client";

import { cn } from "@/lib/utils";

interface CorrelationPair {
  tickerA: string;
  tickerB: string;
  value: number;
}

interface CorrelationTableProps {
  tickers: string[];
  matrix: number[][];
  className?: string;
}

function interpret(value: number): { label: string; colorClass: string } {
  const abs = Math.abs(value);
  if (abs > 0.7) return { label: "Highly correlated", colorClass: "text-loss" };
  if (abs > 0.3) return { label: "Moderate", colorClass: "text-warning" };
  return { label: "Low correlation", colorClass: "text-gain" };
}

export function CorrelationTable({
  tickers,
  matrix,
  className,
}: CorrelationTableProps) {
  // Extract unique pairs (upper triangle only)
  const pairs: CorrelationPair[] = [];
  for (let i = 0; i < tickers.length; i++) {
    for (let j = i + 1; j < tickers.length; j++) {
      pairs.push({
        tickerA: tickers[i],
        tickerB: tickers[j],
        value: matrix[i][j],
      });
    }
  }

  // Sort by absolute correlation descending
  pairs.sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  return (
    <div className={cn("space-y-1.5", className)}>
      {pairs.map((pair) => {
        const { label, colorClass } = interpret(pair.value);
        return (
          <div
            key={`${pair.tickerA}-${pair.tickerB}`}
            className="flex items-center justify-between rounded-md bg-muted/20 px-3 py-2"
          >
            <span className="text-sm font-mono text-foreground">
              {pair.tickerA}{" "}
              <span className="text-subtle">↔</span>{" "}
              {pair.tickerB}
            </span>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "text-sm font-mono tabular-nums font-medium",
                  colorClass
                )}
              >
                {pair.value.toFixed(2)}
              </span>
              <span className="text-xs text-subtle">{label}</span>
            </div>
          </div>
        );
      })}
      {pairs.length === 0 && (
        <p className="text-sm text-subtle text-center py-4">
          Select at least 2 tickers to see correlations.
        </p>
      )}
    </div>
  );
}
