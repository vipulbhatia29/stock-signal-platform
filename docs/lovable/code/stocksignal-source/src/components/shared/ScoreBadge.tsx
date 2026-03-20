import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number;
  size?: "xs" | "sm" | "md";
}

export function ScoreBadge({ score, size = "md" }: ScoreBadgeProps) {
  const color = score >= 8 ? "bg-gain/15 text-gain border-gain/25"
    : score >= 5 ? "bg-warning/15 text-warning border-warning/25"
    : "bg-loss/15 text-loss border-loss/25";

  return (
    <span className={cn(
      "inline-flex items-center justify-center rounded border font-mono font-semibold tabular-nums",
      color,
      size === "xs" ? "h-4 min-w-[22px] px-1 text-[9px]" :
      size === "sm" ? "h-5 min-w-[28px] px-1 text-[10px]" :
      "h-6 min-w-[34px] px-1.5 text-xs"
    )}>
      {score.toFixed(1)}
    </span>
  );
}
