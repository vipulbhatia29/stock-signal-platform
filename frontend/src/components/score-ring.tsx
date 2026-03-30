import { cn } from "@/lib/utils";

interface ScoreRingProps {
  score: number;
  label?: string;
  className?: string;
}

function getScoreVariant(score: number): "buy" | "watch" | "sell" {
  if (score >= 8) return "buy";
  if (score >= 5) return "watch";
  return "sell";
}

export function ScoreRing({ score, label, className }: ScoreRingProps) {
  const variant = getScoreVariant(score);
  return (
    <div
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold",
        variant === "buy" &&
          "border-2 border-gain/30 bg-gain/12 text-[var(--gain)]",
        variant === "watch" &&
          "border-2 border-warning/30 bg-warning/12 text-[var(--warning)]",
        variant === "sell" &&
          "border-2 border-loss/30 bg-loss/12 text-[var(--loss)]",
        className,
      )}
      aria-label={`Composite score ${score} out of 10${label ? `, ${label}` : ""}`}
    >
      {score.toFixed(1)}
    </div>
  );
}
