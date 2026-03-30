import { cn } from "@/lib/utils";

interface MoverRowProps {
  ticker: string;
  price?: number | null;
  changePct: number;
  macdSignal?: string | null;
  onClick?: () => void;
}

export function MoverRow({
  ticker,
  price,
  changePct,
  macdSignal,
  onClick,
}: MoverRowProps) {
  const isGainer = changePct >= 0;
  const macdLabel = macdSignal?.toLowerCase().includes("bullish")
    ? "MACD \u2191"
    : macdSignal?.toLowerCase().includes("bearish")
      ? "MACD \u2193"
      : null;
  return (
    <button
      className={cn(
        "flex w-full items-center justify-between rounded-lg bg-[rgba(15,23,42,0.5)] px-3 py-1.5",
        isGainer
          ? "border-l-[3px] border-l-[var(--gain)]"
          : "border-l-[3px] border-l-[var(--loss)]",
      )}
      onClick={onClick}
      aria-label={`${ticker}${price != null ? `, $${price.toFixed(2)}` : ""}, ${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%`}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">{ticker}</span>
        {price != null && (
          <span className="text-xs text-muted-foreground">
            ${price.toFixed(2)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {macdLabel && (
          <span className="text-[10px] text-muted-foreground">{macdLabel}</span>
        )}
        <span
          className={cn(
            "text-sm font-bold",
            isGainer ? "text-[var(--gain)]" : "text-[var(--loss)]",
          )}
        >
          {isGainer ? "+" : ""}
          {changePct.toFixed(1)}%
        </span>
      </div>
    </button>
  );
}
