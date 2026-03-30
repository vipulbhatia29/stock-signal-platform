// NYSE/NASDAQ trading hours utility with FINRA holiday support.

// FINRA observed holidays for 2026 (update annually)
const HOLIDAYS_2026 = [
  "2026-01-01", // New Year's Day
  "2026-01-19", // MLK Day
  "2026-02-16", // Presidents' Day
  "2026-04-03", // Good Friday
  "2026-05-25", // Memorial Day
  "2026-06-19", // Juneteenth
  "2026-07-03", // Independence Day (observed)
  "2026-09-07", // Labor Day
  "2026-11-26", // Thanksgiving
  "2026-12-25", // Christmas
];

/**
 * Returns true if US equity markets are currently open.
 * Accounts for weekends, FINRA holidays, and DST transitions.
 */
export function isMarketOpen(now: Date = new Date()): boolean {
  const etFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  });

  const parts = etFormatter.formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value;
  const hour = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0");
  const minute = parseInt(
    parts.find((p) => p.type === "minute")?.value ?? "0",
  );

  if (weekday === "Sat" || weekday === "Sun") return false;

  // Holiday check — use ET date, not UTC
  const etDateFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
  });
  const dateStr = etDateFormatter.format(now);
  if (HOLIDAYS_2026.includes(dateStr)) return false;

  const minutesSinceMidnight = hour * 60 + minute;
  const openMinute = 9 * 60 + 30;
  const closeMinute = 16 * 60;

  return minutesSinceMidnight >= openMinute && minutesSinceMidnight < closeMinute;
}

/** @deprecated Use isMarketOpen instead */
export const isNYSEOpen = isMarketOpen;
