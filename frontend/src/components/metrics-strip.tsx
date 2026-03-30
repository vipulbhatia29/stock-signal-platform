import { cn } from "@/lib/utils";

export interface MetricChip {
  label: string;
  value: string;
  sentiment: "positive" | "negative" | "warning" | "neutral";
  primary?: boolean;
}

interface MetricsStripProps {
  metrics: MetricChip[];
  maxVisible?: number;
  className?: string;
}

const SENTIMENT_COLORS: Record<MetricChip["sentiment"], string> = {
  positive: "text-[var(--gain)]",
  negative: "text-[var(--loss)]",
  warning: "text-[var(--warning)]",
  neutral: "text-foreground",
};

export function MetricsStrip({
  metrics,
  maxVisible = 6,
  className,
}: MetricsStripProps) {
  return (
    <div className={cn("flex flex-wrap gap-0.5", className)}>
      {metrics.map((m, i) => (
        <div
          key={m.label}
          data-primary={m.primary || undefined}
          className={cn(
            "flex items-center gap-1 rounded-md bg-[rgba(15,23,42,0.6)] px-2 py-1 text-[11px]",
            i >= maxVisible && "hidden md:flex",
          )}
        >
          <span className="font-medium text-muted-foreground">{m.label}</span>
          <span className={cn("font-semibold", SENTIMENT_COLORS[m.sentiment])}>
            {m.value}
          </span>
        </div>
      ))}
    </div>
  );
}
