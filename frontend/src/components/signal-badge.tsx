import { cn } from "@/lib/utils";
import {
  signalToSentiment,
  formatSignalLabel,
  SENTIMENT_CLASSES,
  SENTIMENT_BG_CLASSES,
} from "@/lib/signals";

interface SignalBadgeProps {
  signal: string | null;
  type: "rsi" | "macd" | "sma" | "bollinger";
}

export function SignalBadge({ signal, type }: SignalBadgeProps) {
  const sentiment = signalToSentiment(signal, type);
  const label = formatSignalLabel(signal);

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium",
        SENTIMENT_BG_CLASSES[sentiment],
        SENTIMENT_CLASSES[sentiment]
      )}
    >
      {label}
    </span>
  );
}
