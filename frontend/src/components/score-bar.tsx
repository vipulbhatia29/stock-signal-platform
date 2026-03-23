import { cn } from "@/lib/utils";

interface ScoreBarProps {
  score: number;
  max?: number;
  segments?: number;
  className?: string;
}

export function ScoreBar({ score, max = 10, segments = 10, className }: ScoreBarProps) {
  const filled = Math.round((score / max) * segments);
  const color = score >= 8 ? "bg-gain" : score >= 5 ? "bg-warning" : "bg-loss";

  return (
    <div className={cn("flex gap-0.5", className)}>
      {Array.from({ length: segments }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-2 flex-1 rounded-sm transition-colors",
            i < filled ? color : "bg-muted/50"
          )}
        />
      ))}
    </div>
  );
}
