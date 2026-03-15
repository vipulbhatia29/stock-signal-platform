// NYSE trading hours utility — purely time-based, no API call.
// Does not account for market holidays (acceptable for status chip display).

/**
 * Returns true if NYSE is currently open based on time alone.
 * Ignores public holidays — for display purposes only.
 */
export function isNYSEOpen(date: Date = new Date()): boolean {
  // Convert to America/New_York timezone
  const nyTime = new Date(
    date.toLocaleString("en-US", { timeZone: "America/New_York" })
  );

  const day = nyTime.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;

  const hours = nyTime.getHours();
  const minutes = nyTime.getMinutes();
  const timeInMinutes = hours * 60 + minutes;

  const openTime = 9 * 60 + 30; // 09:30
  const closeTime = 16 * 60; // 16:00

  return timeInMinutes >= openTime && timeInMinutes < closeTime;
}
