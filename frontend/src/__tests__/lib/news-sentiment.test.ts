import { classifyNewsSentiment } from "@/lib/news-sentiment";

describe("classifyNewsSentiment", () => {
  it("classifies bullish headlines", () => {
    expect(classifyNewsSentiment("Microsoft Azure revenue beats estimates")).toBe("bullish");
    expect(classifyNewsSentiment("Stock surges on earnings report")).toBe("bullish");
    expect(classifyNewsSentiment("Analyst upgrades to buy")).toBe("bullish");
  });

  it("classifies bearish headlines", () => {
    expect(classifyNewsSentiment("Intel delays chip production")).toBe("bearish");
    expect(classifyNewsSentiment("Analysts cut price target")).toBe("bearish");
    expect(classifyNewsSentiment("Stock falls on weak guidance")).toBe("bearish");
  });

  it("classifies neutral headlines", () => {
    expect(classifyNewsSentiment("Company announces quarterly results")).toBe("neutral");
    expect(classifyNewsSentiment("CEO discusses strategy at conference")).toBe("neutral");
  });

  it("is case-insensitive", () => {
    expect(classifyNewsSentiment("STOCK SURGES AFTER EARNINGS")).toBe("bullish");
  });

  it("returns neutral for conflicting keywords", () => {
    expect(classifyNewsSentiment("Stock surges despite analyst cuts")).toBe("neutral");
  });
});
