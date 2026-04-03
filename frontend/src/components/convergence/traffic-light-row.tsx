"use client";

import { cn } from "@/lib/utils";
import type { SignalDirectionDetail, SignalDirectionType } from "@/types/api";

const SIGNAL_LABELS: Record<string, string> = {
  rsi: "RSI",
  macd: "MACD",
  sma: "SMA",
  piotroski: "F-Score",
  forecast: "Forecast",
  news: "News",
};

const DIRECTION_COLORS: Record<SignalDirectionType, string> = {
  bullish: "bg-gain",
  bearish: "bg-loss",
  neutral: "bg-subtle",
};

const DIRECTION_LABELS: Record<SignalDirectionType, string> = {
  bullish: "Bullish",
  bearish: "Bearish",
  neutral: "Neutral",
};

interface TrafficLightRowProps {
  signals: SignalDirectionDetail[];
  className?: string;
}

/** Six signal direction indicators — circles on desktop, badges on mobile. */
export function TrafficLightRow({ signals, className }: TrafficLightRowProps) {
  return (
    <div
      className={cn("flex flex-wrap items-center gap-3", className)}
      role="list"
      aria-label="Signal convergence indicators"
    >
      {signals.map((sig, i) => (
        <div
          key={sig.signal}
          role="listitem"
          aria-label={`${SIGNAL_LABELS[sig.signal] ?? sig.signal}: ${DIRECTION_LABELS[sig.direction]}`}
          className="flex items-center gap-1.5 animate-fade-in"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          {/* Circle indicator */}
          <span
            className={cn(
              "inline-block h-3 w-3 rounded-full shrink-0",
              DIRECTION_COLORS[sig.direction],
            )}
          />
          {/* Label — hidden on small screens, replaced by badge */}
          <span className="hidden text-xs text-muted-foreground sm:inline">
            {SIGNAL_LABELS[sig.signal] ?? sig.signal}
          </span>
          {/* Badge for mobile — shows abbreviated label + direction */}
          <span
            className={cn(
              "inline rounded px-1.5 py-0.5 text-[10px] font-medium sm:hidden",
              sig.direction === "bullish" && "bg-gain/15 text-gain",
              sig.direction === "bearish" && "bg-loss/15 text-loss",
              sig.direction === "neutral" && "bg-subtle/15 text-subtle",
            )}
          >
            {SIGNAL_LABELS[sig.signal] ?? sig.signal}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Skeleton placeholder for loading state. */
export function TrafficLightRowSkeleton() {
  return (
    <div className="flex items-center gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-border animate-pulse" />
          <span className="hidden h-3 w-8 rounded bg-border animate-pulse sm:inline-block" />
        </div>
      ))}
    </div>
  );
}
