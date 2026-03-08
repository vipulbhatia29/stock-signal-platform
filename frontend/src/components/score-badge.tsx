import { cn } from "@/lib/utils";
import {
  scoreToSentiment,
  SENTIMENT_CLASSES,
  SENTIMENT_BG_CLASSES,
} from "@/lib/signals";

interface ScoreBadgeProps {
  score: number | null;
  size?: "sm" | "default" | "lg";
}

export function ScoreBadge({ score, size = "default" }: ScoreBadgeProps) {
  const sentiment = scoreToSentiment(score);

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md font-semibold tabular-nums",
        SENTIMENT_BG_CLASSES[sentiment],
        SENTIMENT_CLASSES[sentiment],
        size === "sm" && "px-1.5 py-0.5 text-xs",
        size === "default" && "px-2 py-0.5 text-sm",
        size === "lg" && "px-3 py-1 text-lg"
      )}
    >
      {score !== null ? score.toFixed(1) : "N/A"}
    </span>
  );
}
