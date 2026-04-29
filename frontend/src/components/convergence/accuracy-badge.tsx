"use client";

import { cn } from "@/lib/utils";
import type { ModelAccuracy } from "@/types/api";

interface AccuracyBadgeProps {
  accuracy: ModelAccuracy | null;
  className?: string;
  onClick?: () => void;
}

function getAccuracyTier(accuracy: ModelAccuracy): {
  label: string;
  classes: string;
} {
  const hitRate = accuracy.direction_hit_rate;
  if (hitRate >= 0.70) {
    return { label: "High", classes: "bg-gain/15 text-gain border-gain/25" };
  }
  if (hitRate >= 0.55) {
    return {
      label: "Medium",
      classes: "bg-warning/15 text-warning border-warning/25",
    };
  }
  return { label: "Low", classes: "bg-loss/15 text-loss border-loss/25" };
}

export function AccuracyBadge({ accuracy, className, onClick }: AccuracyBadgeProps) {
  if (accuracy === null) return null;

  const tier = getAccuracyTier(accuracy);
  const hitPct = Math.round(accuracy.direction_hit_rate * 100);
  const Tag = onClick ? "button" : "span";

  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5",
        "text-[10px] font-medium",
        tier.classes,
        onClick && "cursor-pointer hover:opacity-80 transition-opacity",
        className,
      )}
      aria-label={`Forecast accuracy: ${tier.label} (${hitPct}% direction hit rate, ${accuracy.avg_error_pct.toFixed(1)}% avg error)`}
    >
      {tier.label}
      <span className="font-mono">{hitPct}%</span>
    </Tag>
  );
}
