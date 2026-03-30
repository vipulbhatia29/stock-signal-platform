import { isMarketOpen, isNYSEOpen } from "../market-hours";

describe("isMarketOpen", () => {
  // NYSE hours: Mon-Fri 09:30–16:00 America/New_York

  it("returns true during market hours on weekday", () => {
    // Wednesday March 25, 2026 at 10:00 AM ET = 14:00 UTC
    const date = new Date("2026-03-25T14:00:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });

  it("returns false on weekend", () => {
    // Saturday March 28, 2026
    const date = new Date("2026-03-28T14:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns false before market open", () => {
    // 09:00 ET = 13:00 UTC (EDT)
    const date = new Date("2026-03-25T13:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns false after market close", () => {
    // 16:30 ET = 20:30 UTC (EDT)
    const date = new Date("2026-03-25T20:30:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns true exactly at 09:30 ET", () => {
    // 2026-03-16 09:30 EDT = 13:30 UTC
    const date = new Date("2026-03-16T13:30:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });

  it("returns false exactly at 16:00 ET (market closed)", () => {
    // 2026-03-16 16:00 EDT = 20:00 UTC
    const date = new Date("2026-03-16T20:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("handles EST correctly (November, UTC-5)", () => {
    // Nov 4, 2026 10:00 EST = 15:00 UTC
    const date = new Date("2026-11-04T15:00:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });

  it("returns false on FINRA holiday (New Years Day)", () => {
    const date = new Date("2026-01-01T15:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns false on FINRA holiday (Christmas)", () => {
    const date = new Date("2026-12-25T15:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns true on day before holiday during hours", () => {
    // Dec 24, 2026 is a Thursday (not a holiday)
    const date = new Date("2026-12-24T15:00:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });
});

describe("isNYSEOpen (backward compat)", () => {
  it("is an alias for isMarketOpen", () => {
    expect(isNYSEOpen).toBe(isMarketOpen);
  });

  it("works the same as isMarketOpen", () => {
    const date = new Date("2026-03-25T14:00:00Z");
    expect(isNYSEOpen(date)).toBe(true);
  });
});
