"use client";

import { cn } from "@/lib/utils";

interface AccuracyBadgeProps {
  /** MAPE percentage (e.g. 8.5 means 8.5% error). */
  mape: number | null;
  className?: string;
  /** Optional click handler — typically opens a DrillDownSheet. */
  onClick?: () => void;
}

function getAccuracyTier(mape: number): {
  label: string;
  classes: string;
} {
  if (mape <= 5) {
    return { label: "High", classes: "bg-gain/15 text-gain border-gain/25" };
  }
  if (mape <= 15) {
    return {
      label: "Medium",
      classes: "bg-warning/15 text-warning border-warning/25",
    };
  }
  return { label: "Low", classes: "bg-loss/15 text-loss border-loss/25" };
}

/** Compact badge showing forecast accuracy (MAPE%). Clickable for drill-down. */
export function AccuracyBadge({ mape, className, onClick }: AccuracyBadgeProps) {
  if (mape === null) return null;

  const tier = getAccuracyTier(mape);
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
      aria-label={`Forecast accuracy: ${tier.label} (${mape.toFixed(1)}% error)`}
    >
      {tier.label} accuracy
      <span className="font-mono">{mape.toFixed(1)}%</span>
    </Tag>
  );
}
