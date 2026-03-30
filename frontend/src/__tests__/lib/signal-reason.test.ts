import { buildSignalReason } from "@/lib/signal-reason";

describe("buildSignalReason", () => {
  it("builds reason from MACD + RSI", () => {
    const reason = buildSignalReason({
      macd_signal: "bullish_crossover",
      rsi_value: 34,
      rsi_signal: "oversold",
    });
    expect(reason).toContain("MACD bullish crossover");
    expect(reason).toContain("RSI oversold");
  });

  it("includes Piotroski when strong", () => {
    const reason = buildSignalReason({
      macd_signal: "bullish",
      piotroski_score: 8,
    });
    expect(reason).toContain("Piotroski 8/9");
  });

  it("returns empty string with no data", () => {
    expect(buildSignalReason({})).toBe("");
  });

  it("limits to 3 factors", () => {
    const reason = buildSignalReason({
      macd_signal: "bullish_crossover",
      rsi_value: 30,
      rsi_signal: "oversold",
      piotroski_score: 8,
      sma_signal: "golden_cross",
      pe_ratio: 15,
    });
    const factors = reason.split(" + ");
    expect(factors.length).toBeLessThanOrEqual(3);
  });
});
