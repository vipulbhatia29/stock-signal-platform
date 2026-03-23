/**
 * Build a CSV string from an array of objects.
 * Handles quoting for strings with commas, quotes, or newlines.
 */
export function buildCSV(data: Record<string, unknown>[]): string {
  if (!data.length) return "";

  const headers = Object.keys(data[0]);

  function escapeField(value: unknown): string {
    if (value == null) return "";
    const str = String(value);
    if (/[",\n\r]/.test(str)) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    // Quote all strings for consistency
    if (typeof value === "string") return `"${str}"`;
    return str;
  }

  const rows = data.map((row) =>
    headers.map((h) => escapeField(row[h])).join(",")
  );

  return [headers.join(","), ...rows].join("\n");
}

/**
 * Trigger a CSV file download in the browser.
 */
export function downloadCSV(
  filename: string,
  data: Record<string, unknown>[]
): void {
  const csv = buildCSV(data);
  if (!csv) return;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
