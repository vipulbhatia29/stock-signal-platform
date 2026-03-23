// ChangeIndicator — displays a signed numeric change with color.
// Combines color + sign for color-blind safety. Icon optional.

import { TrendingUpIcon, TrendingDownIcon, MinusIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatPercent, formatCurrency } from "@/lib/format";

interface ChangeIndicatorProps {
  value: number | null;
  format?: "percent" | "currency";
  size?: "sm" | "default";
  prefix?: string;
  showSign?: boolean;
  showIcon?: boolean;
  className?: string;
}

export function ChangeIndicator({
  value,
  format = "percent",
  size = "default",
  prefix = "",
  showSign = true,
  showIcon = true,
  className,
}: ChangeIndicatorProps) {
  if (value === null) {
    return (
      <span className={cn("text-subtle", className)}>—</span>
    );
  }

  const isPositive = value > 0;
  const isNegative = value < 0;
  const formatted =
    format === "percent" ? formatPercent(value) : formatCurrency(value);
  const sign = showSign && isPositive ? "+" : "";

  const iconSize = size === "sm" ? "size-3" : "size-4";
  const textSize = size === "sm" ? "text-xs" : "text-sm";

  const colorClass = isPositive
    ? "text-gain"
    : isNegative
      ? "text-loss"
      : "text-subtle";

  const Icon = isPositive
    ? TrendingUpIcon
    : isNegative
      ? TrendingDownIcon
      : MinusIcon;

  return (
    <span
      className={cn("inline-flex items-center gap-1 font-mono font-medium tabular-nums", textSize, colorClass, className)}
      aria-label={`${isPositive ? "up" : isNegative ? "down" : "unchanged"} ${sign}${prefix}${formatted}`}
    >
      {showIcon && <Icon className={iconSize} aria-hidden="true" />}
      {sign}{prefix}{formatted}
    </span>
  );
}
