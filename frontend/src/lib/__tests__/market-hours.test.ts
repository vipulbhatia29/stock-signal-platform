import { isNYSEOpen } from "../market-hours";

describe("isNYSEOpen", () => {
  // NYSE hours: Mon-Fri 09:30–16:00 America/New_York

  it("returns true on a weekday at 10am ET", () => {
    // 2026-03-16 Monday 10:00 ET = 15:00 UTC
    const date = new Date("2026-03-16T15:00:00Z");
    expect(isNYSEOpen(date)).toBe(true);
  });

  it("returns false before 09:30 ET on a weekday", () => {
    // 2026-03-16 Monday 09:00 EDT = 13:00 UTC (EDT is UTC-4, in effect after Mar 8 DST change)
    const date = new Date("2026-03-16T13:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns false after 16:00 ET on a weekday", () => {
    // 2026-03-16 Monday 16:30 ET = 21:30 UTC
    const date = new Date("2026-03-16T21:30:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns false on Saturday", () => {
    // 2026-03-21 Saturday 12:00 ET = 17:00 UTC
    const date = new Date("2026-03-21T17:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns false on Sunday", () => {
    const date = new Date("2026-03-22T17:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns true exactly at 09:30 ET", () => {
    // 2026-03-16 09:30 EDT = 13:30 UTC (EDT is UTC-4, in effect after Mar 8 DST change)
    const date = new Date("2026-03-16T13:30:00Z");
    expect(isNYSEOpen(date)).toBe(true);
  });

  it("returns false exactly at 16:00 ET (market closed)", () => {
    const date = new Date("2026-03-16T20:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });
});
