"use client";

import { cn } from "@/lib/utils";

interface GaugeBarProps {
  value: number;
  max?: number;
  label?: string;
  thresholds?: { warn: number; critical: number };
}

export function GaugeBar({
  value,
  max = 100,
  label,
  thresholds = { warn: 60, critical: 85 },
}: GaugeBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));

  let color: string;
  if (pct >= thresholds.critical) {
    color = "bg-red-500";
  } else if (pct >= thresholds.warn) {
    color = "bg-yellow-400";
  } else {
    color = "bg-cyan";
  }

  return (
    <div data-testid="gauge-bar" className="w-full">
      {label && (
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-subtle">{label}</span>
          <span className="text-xs font-mono text-muted-foreground">
            {pct.toFixed(0)}%
          </span>
        </div>
      )}
      <div className="h-2 w-full rounded-full bg-card2 overflow-hidden">
        <div
          className={cn("h-2 rounded-full transition-all duration-500", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
