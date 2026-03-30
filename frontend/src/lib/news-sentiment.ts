export type NewsSentiment = "bullish" | "bearish" | "neutral";

const BULLISH_KEYWORDS = [
  "beats",
  "surges",
  "upgrades",
  "accelerates",
  "record",
  "growth",
  "rises",
  "soars",
  "rally",
  "gains",
  "jumps",
  "outperforms",
  "exceeds",
  "boost",
  "strong",
];

const BEARISH_KEYWORDS = [
  "misses",
  "delays",
  "cut",
  "cuts",
  "rejects",
  "falls",
  "downgrades",
  "warns",
  "drops",
  "declines",
  "plunges",
  "slumps",
  "losses",
  "weak",
  "disappoints",
  "layoffs",
];

export function classifyNewsSentiment(title: string): NewsSentiment {
  const lower = title.toLowerCase();
  const hasBullish = BULLISH_KEYWORDS.some((kw) => lower.includes(kw));
  const hasBearish = BEARISH_KEYWORDS.some((kw) => lower.includes(kw));

  if (hasBullish && !hasBearish) return "bullish";
  if (hasBearish && !hasBullish) return "bearish";
  return "neutral";
}
