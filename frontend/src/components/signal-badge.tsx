import { cn } from "@/lib/utils";
import {
  signalToSentiment,
  formatSignalLabel,
  SENTIMENT_CLASSES,
  SENTIMENT_BG_CLASSES,
} from "@/lib/signals";

const RECOMMENDATION_STYLES: Record<"BUY" | "HOLD" | "SELL", string> = {
  BUY:  "bg-[var(--gdim)] text-gain border border-[rgba(34,211,160,.2)]",
  HOLD: "bg-[var(--wdim)] text-warning border border-[rgba(251,191,36,.18)]",
  SELL: "bg-[var(--ldim)] text-loss border border-[rgba(248,113,113,.2)]",
};

const RECOMMENDATION_BASE =
  "font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] rounded-full px-2 py-0.5 inline-flex items-center";

interface SignalBadgeProps {
  signal: string | null;
  type?: "rsi" | "macd" | "sma" | "bollinger" | "recommendation";
}

export function SignalBadge({ signal, type }: SignalBadgeProps) {
  // Recommendation pill style for BUY/HOLD/SELL
  if (signal === "BUY" || signal === "HOLD" || signal === "SELL") {
    return (
      <span
        className={cn(RECOMMENDATION_BASE, RECOMMENDATION_STYLES[signal])}
        aria-label={`Signal: ${signal}`}
      >
        {signal}
      </span>
    );
  }

  const resolvedType = type ?? "rsi";
  const sentiment = signalToSentiment(signal, resolvedType as "rsi" | "macd" | "sma" | "bollinger");
  const label = formatSignalLabel(signal);

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium",
        SENTIMENT_BG_CLASSES[sentiment],
        SENTIMENT_CLASSES[sentiment]
      )}
      aria-label={`${resolvedType.toUpperCase()} signal: ${label}, ${sentiment}`}
    >
      {label}
    </span>
  );
}
