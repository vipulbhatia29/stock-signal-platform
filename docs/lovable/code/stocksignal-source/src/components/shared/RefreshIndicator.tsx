import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useStockRefresh } from "@/contexts/StockRefreshContext";

function formatRelativeTime(date: Date | undefined): string {
  if (!date) return "never";
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function isStale(date: Date | undefined): boolean {
  if (!date) return true;
  return Date.now() - date.getTime() > 12 * 3600000; // >12 hours = stale
}

interface RefreshIndicatorProps {
  ticker: string;
  className?: string;
  /** Compact mode: just the icon, no text */
  compact?: boolean;
}

export function RefreshIndicator({ ticker, className, compact = false }: RefreshIndicatorProps) {
  const { lastRefreshed, refreshing, refreshStock } = useStockRefresh();
  const ts = lastRefreshed[ticker];
  const isRefreshing = refreshing[ticker];
  const stale = isStale(ts);

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isRefreshing) refreshStock(ticker);
  };

  return (
    <button
      onClick={handleClick}
      title={`Last refreshed: ${ts ? ts.toLocaleString() : "never"}${stale ? " (stale)" : ""}`}
      className={cn(
        "inline-flex items-center gap-1 rounded px-1 py-0.5 text-[9px] transition-colors",
        stale && !isRefreshing
          ? "text-warning hover:text-warning/80 hover:bg-warning/10"
          : "text-muted-foreground hover:text-foreground hover:bg-muted/30",
        isRefreshing && "pointer-events-none",
        className,
      )}
    >
      <RefreshCw className={cn("h-2.5 w-2.5", isRefreshing && "animate-spin")} />
      {!compact && (
        <span className="font-mono">{isRefreshing ? "…" : formatRelativeTime(ts)}</span>
      )}
    </button>
  );
}
