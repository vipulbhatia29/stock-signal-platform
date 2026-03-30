import { cn } from "@/lib/utils";

interface AlertTileProps {
  title: string;
  ticker?: string;
  severity: "critical" | "high" | "medium" | "low";
  message?: string;
  timestamp?: string;
  className?: string;
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: "border-l-[var(--loss)] bg-loss/5",
  high: "border-l-[var(--warning)] bg-warning/5",
  medium: "border-l-blue-500 bg-blue-500/5",
  low: "border-l-muted-foreground bg-muted/5",
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: "CRITICAL",
  high: "HIGH",
  medium: "MEDIUM",
  low: "LOW",
};

export function AlertTile({ title, ticker, severity, message, timestamp, className }: AlertTileProps) {
  return (
    <div className={cn(
      "rounded-lg border border-border/20 border-l-[3px] p-3",
      SEVERITY_STYLES[severity],
      className,
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={cn(
            "text-[10px] font-bold uppercase tracking-wider",
            severity === "critical" && "text-[var(--loss)]",
            severity === "high" && "text-[var(--warning)]",
            severity === "medium" && "text-blue-400",
            severity === "low" && "text-muted-foreground",
          )}>
            {SEVERITY_LABELS[severity]}
          </span>
          {ticker && <span className="text-xs font-semibold">{ticker}</span>}
        </div>
        {timestamp && <span className="text-[10px] text-muted-foreground">{timestamp}</span>}
      </div>
      <div className="mt-1 text-sm font-medium text-foreground">{title}</div>
      {message && <div className="mt-0.5 text-[11px] text-muted-foreground">{message}</div>}
    </div>
  );
}
