"use client";
import { cn } from "@/lib/utils";
import { ScoreRing } from "./score-ring";
import { ActionBadge } from "./action-badge";
import { MetricsStrip, type MetricChip } from "./metrics-strip";

interface SignalStockCardProps {
  ticker: string;
  name?: string | null;
  compositeScore: number;
  action: string;
  metrics: MetricChip[];
  reason?: string;
  onClick?: () => void;
  className?: string;
}

function getCardVariant(score: number): string {
  if (score >= 8) return "border-gain/15 hover:border-gain/35";
  if (score >= 5) return "border-warning/15 hover:border-warning/35";
  return "border-loss/20 hover:border-loss/40";
}

export function SignalStockCard({
  ticker,
  name,
  compositeScore,
  action,
  metrics,
  reason,
  onClick,
  className,
}: SignalStockCardProps) {
  const variant = getCardVariant(compositeScore);
  const Wrapper = onClick ? "button" : "div";
  return (
    <Wrapper
      className={cn(
        "flex w-full flex-col gap-2 rounded-[10px] border bg-[rgba(15,23,42,0.5)] p-3.5 text-left transition-all",
        variant,
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <ScoreRing score={compositeScore} label={action} />
          <div>
            <div className="text-sm font-semibold text-foreground">
              {ticker}
            </div>
            {name && (
              <div className="text-[11px] text-muted-foreground">{name}</div>
            )}
          </div>
        </div>
        <ActionBadge action={action} />
      </div>
      <MetricsStrip metrics={metrics} maxVisible={4} />
      {reason && (
        <div className="text-[11px] leading-relaxed text-[var(--muted-foreground)]">
          {reason}
        </div>
      )}
    </Wrapper>
  );
}
