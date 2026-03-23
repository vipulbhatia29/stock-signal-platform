"use client";

import { XIcon, AlertTriangleIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExcludedTicker } from "@/types/api";

interface CorrelationTickerChipsProps {
  tickers: string[];
  onRemove: (ticker: string) => void;
  excludedTickers?: ExcludedTicker[];
  maxTickers?: number;
  className?: string;
}

export function CorrelationTickerChips({
  tickers,
  onRemove,
  excludedTickers = [],
  maxTickers = 15,
  className,
}: CorrelationTickerChipsProps) {
  const isAtCap = tickers.length >= maxTickers;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {tickers.map((ticker) => (
        <span
          key={ticker}
          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-mono font-medium text-primary"
        >
          {ticker}
          <button
            type="button"
            onClick={() => onRemove(ticker)}
            className="rounded-full p-0.5 hover:bg-primary/20 transition-colors"
            aria-label={`Remove ${ticker}`}
          >
            <XIcon className="size-3" />
          </button>
        </span>
      ))}

      {excludedTickers.map((excluded) => (
        <span
          key={excluded.ticker}
          className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2.5 py-1 text-xs font-mono text-warning"
          title={excluded.reason}
        >
          <AlertTriangleIcon className="size-3" />
          {excluded.ticker}
        </span>
      ))}

      {isAtCap && (
        <span className="text-xs text-subtle">
          Max {maxTickers} tickers
        </span>
      )}
    </div>
  );
}
