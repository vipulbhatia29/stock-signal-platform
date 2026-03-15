// MetricCard — standardized KPI display block (label + value + optional change).
// Callers wrap in Card if needed. Use MetricCardSkeleton for loading state.

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ChangeIndicator } from "@/components/change-indicator";

interface MetricCardProps {
  label: string;
  value: string | number | null;
  change?: number | null;
  formatChange?: "percent" | "currency";
  icon?: React.ReactNode;
  className?: string;
  valueClassName?: string;
}

export function MetricCard({
  label,
  value,
  change,
  formatChange = "percent",
  icon,
  className,
  valueClassName,
}: MetricCardProps) {
  const displayValue = value === null || value === undefined ? "—" : value;

  return (
    <div className={cn("bg-card2 border border-border rounded-[var(--radius)] p-[10px_13px]", className)}>
      <p className="flex items-center gap-1 text-[9px] uppercase tracking-[0.08em] text-subtle mb-1">
        {icon && <span aria-hidden="true">{icon}</span>}
        {label}
      </p>
      <p className={cn("font-mono text-[16px] font-semibold text-foreground", valueClassName)}>
        {displayValue}
      </p>
      {change != null && (
        <ChangeIndicator value={change} format={formatChange} size="sm" />
      )}
    </div>
  );
}

export function MetricCardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-6 w-16" />
    </div>
  );
}
