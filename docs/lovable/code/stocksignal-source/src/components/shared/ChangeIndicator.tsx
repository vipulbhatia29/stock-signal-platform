import { cn } from "@/lib/utils";

interface ChangeIndicatorProps {
  value: number;
  suffix?: string;
  prefix?: string;
  className?: string;
  showSign?: boolean;
}

export function ChangeIndicator({ value, suffix = "%", prefix = "", className, showSign = true }: ChangeIndicatorProps) {
  const isPositive = value > 0;
  const isZero = value === 0;
  return (
    <span className={cn(
      "font-mono tabular-nums",
      isZero ? "text-muted-foreground" : isPositive ? "text-gain" : "text-loss",
      className
    )}>
      {prefix}{showSign && isPositive ? "+" : ""}{value.toFixed(2)}{suffix}
    </span>
  );
}
