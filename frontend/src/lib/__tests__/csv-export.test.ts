import { buildCSV } from "../csv-export";

describe("buildCSV", () => {
  it("generates headers and rows", () => {
    const csv = buildCSV([
      { ticker: "AAPL", score: 7.2 },
      { ticker: "MSFT", score: 8.1 },
    ]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("ticker,score");
    expect(lines[1]).toBe('"AAPL",7.2');
    expect(lines[2]).toBe('"MSFT",8.1');
  });

  it("returns empty string for empty data", () => {
    expect(buildCSV([])).toBe("");
  });

  it("escapes commas and quotes in values", () => {
    const csv = buildCSV([{ name: 'Foo, "Bar"', value: 42 }]);
    expect(csv).toContain('"Foo, ""Bar"""');
  });
});
