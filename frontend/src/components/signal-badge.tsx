import { cn } from "@/lib/utils";
import {
  signalToSentiment,
  SENTIMENT_CLASSES,
  SENTIMENT_BG_CLASSES,
} from "@/lib/signals";

/** Direct style map for recommendation and well-known signal values. */
const DIRECT_STYLES: Record<string, string> = {
  BUY:   "bg-gain/15 text-gain border border-gain/20",
  HOLD:  "bg-warning/15 text-warning border border-warning/20",
  SELL:  "bg-loss/15 text-loss border border-loss/20",
  WATCH: "bg-[var(--cdim)] text-cyan border border-[var(--bhi)]",
  AVOID: "bg-loss/15 text-loss border border-loss/20",
  // SMA signals
  GOLDEN_CROSS: "bg-gain/10 text-gain",
  DEATH_CROSS:  "bg-loss/10 text-loss",
  ABOVE_200:    "bg-gain/10 text-gain",
  BELOW_200:    "bg-loss/10 text-loss",
  // Bollinger
  UPPER:  "bg-loss/10 text-loss",
  MIDDLE: "bg-muted text-muted-foreground",
  LOWER:  "bg-gain/10 text-gain",
};

/** Custom display labels for signal values. */
const LABELS: Record<string, string> = {
  GOLDEN_CROSS: "Golden ×",
  DEATH_CROSS:  "Death ×",
  ABOVE_200:    "Above 200",
  BELOW_200:    "Below 200",
};

interface SignalBadgeProps {
  signal: string | null;
  type?: "rsi" | "macd" | "sma" | "bollinger" | "recommendation";
  size?: "sm" | "md";
}

export function SignalBadge({ signal, type, size = "sm" }: SignalBadgeProps) {
  if (!signal) {
    return (
      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground">
        N/A
      </span>
    );
  }

  // Use direct style if available (recommendation + known signals)
  const directStyle = DIRECT_STYLES[signal];
  if (directStyle) {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded font-medium",
          directStyle,
          size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
        )}
        aria-label={`Signal: ${LABELS[signal] || signal}`}
      >
        {LABELS[signal] || signal}
      </span>
    );
  }

  // Fallback: use sentiment-based styling
  const resolvedType = type ?? "rsi";
  const sentiment = signalToSentiment(signal, resolvedType as "rsi" | "macd" | "sma" | "bollinger");
  const label = LABELS[signal] || signal.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <span
      className={cn(
        "inline-flex items-center rounded font-medium",
        SENTIMENT_BG_CLASSES[sentiment],
        SENTIMENT_CLASSES[sentiment],
        size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
      )}
      aria-label={`${resolvedType.toUpperCase()} signal: ${label}, ${sentiment}`}
    >
      {label}
    </span>
  );
}
