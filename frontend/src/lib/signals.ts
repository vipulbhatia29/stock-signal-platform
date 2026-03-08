// Signal color mapping and score classification utilities.

export type Sentiment = "bullish" | "neutral" | "bearish";

export function scoreToSentiment(score: number | null): Sentiment {
  if (score === null) return "neutral";
  if (score >= 8) return "bullish";
  if (score >= 5) return "neutral";
  return "bearish";
}

export function rsiToSentiment(signal: string | null): Sentiment {
  if (!signal) return "neutral";
  if (signal === "OVERSOLD") return "bullish";
  if (signal === "OVERBOUGHT") return "bearish";
  return "neutral";
}

export function macdToSentiment(signal: string | null): Sentiment {
  if (!signal) return "neutral";
  if (signal.includes("BULLISH")) return "bullish";
  if (signal.includes("BEARISH")) return "bearish";
  return "neutral";
}

export function smaToSentiment(signal: string | null): Sentiment {
  if (!signal) return "neutral";
  if (signal === "GOLDEN_CROSS" || signal === "ABOVE_200") return "bullish";
  if (signal === "DEATH_CROSS" || signal === "BELOW_200") return "bearish";
  return "neutral";
}

export function bollingerToSentiment(position: string | null): Sentiment {
  if (!position) return "neutral";
  if (position === "LOWER") return "bullish";
  if (position === "UPPER") return "bearish";
  return "neutral";
}

export function signalToSentiment(
  signal: string | null,
  type: "rsi" | "macd" | "sma" | "bollinger"
): Sentiment {
  switch (type) {
    case "rsi":
      return rsiToSentiment(signal);
    case "macd":
      return macdToSentiment(signal);
    case "sma":
      return smaToSentiment(signal);
    case "bollinger":
      return bollingerToSentiment(signal);
  }
}

export function formatSignalLabel(signal: string | null): string {
  if (!signal) return "N/A";
  return signal
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export const SENTIMENT_CLASSES: Record<Sentiment, string> = {
  bullish: "text-emerald-700 dark:text-emerald-400",
  neutral: "text-amber-600 dark:text-amber-400",
  bearish: "text-red-600 dark:text-red-400",
};

export const SENTIMENT_BG_CLASSES: Record<Sentiment, string> = {
  bullish: "bg-emerald-50 dark:bg-emerald-950/30",
  neutral: "bg-amber-50 dark:bg-amber-950/30",
  bearish: "bg-red-50 dark:bg-red-950/30",
};

export const SENTIMENT_BORDER_CLASSES: Record<Sentiment, string> = {
  bullish: "border-emerald-500",
  neutral: "border-amber-500",
  bearish: "border-red-500",
};
