"use client";

import { cn } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";
import type { DivergenceAlert as DivergenceAlertType } from "@/types/api";

interface DivergenceAlertProps {
  divergence: DivergenceAlertType;
  className?: string;
}

/** Amber banner shown when forecast disagrees with technical majority. */
export function DivergenceAlert({
  divergence,
  className,
}: DivergenceAlertProps) {
  if (!divergence.is_divergent) return null;

  const hitPct =
    divergence.historical_hit_rate !== null
      ? Math.round(divergence.historical_hit_rate * 100)
      : null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(
        "flex items-start gap-2.5 rounded-lg border border-warning/25",
        "bg-warning/10 px-3 py-2.5 animate-fade-in",
        className,
      )}
    >
      <AlertTriangle
        className="mt-0.5 h-4 w-4 shrink-0 text-warning"
        aria-hidden="true"
      />
      <div className="text-sm leading-relaxed text-foreground">
        <span className="font-medium">Signal divergence: </span>
        <span>
          Forecast is{" "}
          <span className="font-medium text-warning">
            {divergence.forecast_direction}
          </span>
          , but technical indicators lean{" "}
          <span className="font-medium">{divergence.technical_majority}</span>.
        </span>
        {hitPct !== null && divergence.sample_count !== null && (
          <span className="text-muted-foreground">
            {" "}
            Historically, the forecast was right {hitPct}% of the time (
            {divergence.sample_count} cases).
          </span>
        )}
      </div>
    </div>
  );
}
