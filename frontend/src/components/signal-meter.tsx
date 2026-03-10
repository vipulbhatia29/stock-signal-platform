import { cn } from "@/lib/utils";

interface SignalMeterProps {
  score: number | null;
  size?: "sm" | "default";
}

export function SignalMeter({ score, size = "default" }: SignalMeterProps) {
  const filled = score !== null ? Math.round(score) : 0;

  return (
    <div
      role="meter"
      aria-valuenow={score ?? 0}
      aria-valuemin={0}
      aria-valuemax={10}
      aria-label={
        score !== null
          ? `Signal meter: ${score.toFixed(1)} out of 10`
          : "Signal meter: score not available"
      }
      className="flex w-full gap-0.5"
    >
      {Array.from({ length: 10 }, (_, i) => {
        const isFilled = score !== null && i < filled;
        const segmentColor = isFilled
          ? i <= 3
            ? "bg-loss"
            : i <= 5
              ? "bg-neutral-signal"
              : "bg-gain"
          : "bg-muted/40";

        return (
          <div
            key={i}
            className={cn(
              "flex-1 rounded-sm",
              size === "sm" ? "h-1.5" : "h-2",
              segmentColor
            )}
          />
        );
      })}
    </div>
  );
}
