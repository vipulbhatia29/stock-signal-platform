import { cn } from "@/lib/utils";
import { scoreToSentiment } from "@/lib/signals";

const SCORE_COLOR_CLASSES: Record<string, string> = {
  bullish:  "text-gain bg-[var(--gdim)] border border-[rgba(34,211,160,.2)]",
  neutral:  "text-warning bg-[var(--wdim)] border border-[rgba(251,191,36,.18)]",
  bearish:  "text-loss bg-[var(--ldim)] border border-[rgba(248,113,113,.2)]",
};

interface ScoreBadgeProps {
  score: number | null;
  size?: "xs" | "sm" | "default" | "lg";
}

export function ScoreBadge({ score, size = "default" }: ScoreBadgeProps) {
  const sentiment = scoreToSentiment(score);
  const colorClass = SCORE_COLOR_CLASSES[sentiment] ?? SCORE_COLOR_CLASSES["neutral"];

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-md font-mono font-semibold tabular-nums",
        colorClass,
        size === "xs" && "h-4 min-w-[22px] px-1 text-[9px]",
        size === "sm" && "h-5 min-w-[28px] px-1 text-[10px]",
        size === "default" && "px-2 py-0.5 text-sm",
        size === "lg" && "px-3 py-1 text-lg"
      )}
      aria-label={
        score !== null
          ? `Composite score ${score.toFixed(1)} out of 10, ${sentiment}`
          : "Score not available"
      }
    >
      {score !== null ? score.toFixed(1) : "N/A"}
    </span>
  );
}
