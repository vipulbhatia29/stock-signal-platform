export type NewsSentiment = "bullish" | "bearish" | "neutral";

const BULLISH_KEYWORDS = [
  "surge", "surges", "surging",
  "rally", "rallies", "rallying",
  "soar", "soars", "soaring",
  "jump", "jumps", "jumping",
  "gain", "gains",
  "upgrade", "upgrades", "upgraded",
  "beat", "beats", "beating",
  "outperform", "outperforms",
  "bullish",
  "record high",
  "all-time high",
  "breakout",
  "strong buy",
];

const BEARISH_KEYWORDS = [
  "crash", "crashes", "crashing",
  "plunge", "plunges", "plunging",
  "tumble", "tumbles", "tumbling",
  "drop", "drops", "dropping",
  "fall", "falls", "falling",
  "decline", "declines", "declining",
  "downgrade", "downgrades", "downgraded",
  "miss", "misses",
  "underperform", "underperforms",
  "bearish",
  "sell-off", "selloff",
  "warning",
  "cut", "cuts",
  "loss", "losses",
];

/**
 * Classify news headline sentiment using keyword matching.
 * Returns "bullish", "bearish", or "neutral".
 */
export function classifyNewsSentiment(title: string): NewsSentiment {
  const lower = title.toLowerCase();

  let bullishCount = 0;
  let bearishCount = 0;

  for (const kw of BULLISH_KEYWORDS) {
    if (lower.includes(kw)) bullishCount++;
  }
  for (const kw of BEARISH_KEYWORDS) {
    if (lower.includes(kw)) bearishCount++;
  }

  if (bullishCount > bearishCount) return "bullish";
  if (bearishCount > bullishCount) return "bearish";
  return "neutral";
}
