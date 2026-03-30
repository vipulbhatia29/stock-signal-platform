import { normalizeSector } from "@/lib/sectors";

describe("normalizeSector", () => {
  it("passes through canonical names", () => {
    expect(normalizeSector("Technology")).toBe("Technology");
    expect(normalizeSector("Energy")).toBe("Energy");
  });

  it("normalizes ETF aliases to canonical", () => {
    expect(normalizeSector("Financials")).toBe("Financial Services");
    expect(normalizeSector("Consumer Discretionary")).toBe("Consumer Cyclical");
    expect(normalizeSector("Materials")).toBe("Basic Materials");
  });

  it("returns unknown sectors as-is", () => {
    expect(normalizeSector("Unknown")).toBe("Unknown");
  });
});
