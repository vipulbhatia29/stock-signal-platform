interface SignalData {
  macd_signal?: string | null;
  rsi_value?: number | null;
  rsi_signal?: string | null;
  piotroski_score?: number | null;
  sma_signal?: string | null;
  pe_ratio?: number | null;
  insider_activity?: string | null;
}

const MACD_LABELS: Record<string, string> = {
  bullish_crossover: "MACD bullish crossover",
  bullish: "MACD bullish",
  bearish_crossover: "MACD bearish crossover",
  bearish: "MACD bearish",
};

const SMA_LABELS: Record<string, string> = {
  golden_cross: "SMA golden cross",
  death_cross: "SMA death cross",
  above: "above SMA",
  below: "below SMA",
};

export function buildSignalReason(data: SignalData): string {
  const factors: string[] = [];

  if (data.macd_signal) {
    factors.push(MACD_LABELS[data.macd_signal] ?? `MACD ${data.macd_signal}`);
  }

  if (data.rsi_signal && data.rsi_signal !== "neutral") {
    const val =
      data.rsi_value != null ? ` (${Math.round(data.rsi_value)})` : "";
    factors.push(`RSI ${data.rsi_signal}${val}`);
  }

  if (data.piotroski_score != null && data.piotroski_score >= 7) {
    factors.push(`Piotroski ${data.piotroski_score}/9`);
  }

  if (data.sma_signal) {
    factors.push(SMA_LABELS[data.sma_signal] ?? `SMA ${data.sma_signal}`);
  }

  if (data.pe_ratio != null && data.pe_ratio < 15) {
    factors.push(`P/E ${data.pe_ratio.toFixed(1)}`);
  }

  return factors.slice(0, 3).join(" + ");
}
