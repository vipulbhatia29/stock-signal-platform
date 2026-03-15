// frontend/src/components/relative-time.tsx
"use client";

interface RelativeTimeProps {
  /** ISO date string or Date object */
  date: string | Date;
  /** Verb prefix. Default: "Refreshed" */
  prefix?: string;
}

/**
 * Displays a human-readable relative time string.
 * Examples: "Refreshed just now", "Refreshed 3 hours ago", "Refreshed Mar 4"
 *
 * Display rules:
 * - < 1 hour: "Refreshed just now"
 * - 1-23 hours: "Refreshed 3 hours ago"
 * - 1-6 days: "Refreshed 2 days ago"
 * - >= 7 days: "Refreshed Mar 4" (absolute, MMM D format)
 */
export function RelativeTime({ date, prefix = "Refreshed" }: RelativeTimeProps) {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);
  const diffDays = diffMs / (1000 * 60 * 60 * 24);

  let label: string;

  if (diffHours < 1) {
    label = "just now";
  } else if (diffHours < 24) {
    const h = Math.floor(diffHours);
    label = `${h} ${h === 1 ? "hour" : "hours"} ago`;
  } else if (diffDays < 7) {
    const days = Math.floor(diffDays);
    label = `${days} ${days === 1 ? "day" : "days"} ago`;
  } else {
    label = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  return (
    <span className="text-subtle" title={d.toLocaleString()}>
      {prefix} {label}
    </span>
  );
}
