import { formatMicroCurrency, formatDuration } from "@/lib/format";

describe("formatMicroCurrency", () => {
  it("formats sub-penny values with 4 decimals", () => {
    expect(formatMicroCurrency(0.0012)).toBe("$0.0012");
  });
  it("formats zero", () => {
    expect(formatMicroCurrency(0)).toBe("$0.0000");
  });
  it("formats values >= $1 with 2 decimals", () => {
    expect(formatMicroCurrency(1.5)).toBe("$1.50");
  });
  it("handles null", () => {
    expect(formatMicroCurrency(null)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("formats milliseconds under 1s", () => {
    expect(formatDuration(350)).toBe("350ms");
  });
  it("formats seconds", () => {
    expect(formatDuration(1200)).toBe("1.2s");
  });
  it("formats minutes", () => {
    expect(formatDuration(135000)).toBe("2m 15s");
  });
  it("handles zero", () => {
    expect(formatDuration(0)).toBe("0ms");
  });
  it("handles null", () => {
    expect(formatDuration(null)).toBe("—");
  });
});
