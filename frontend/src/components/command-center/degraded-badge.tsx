"use client";

interface DegradedBadgeProps {
  zones: string[];
}

export function DegradedBadge({ zones }: DegradedBadgeProps) {
  if (zones.length === 0) return null;

  return (
    <span
      data-testid="degraded-badge"
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-1.5 rounded-md bg-yellow-400/10 border border-yellow-400/30 px-2.5 py-1 text-xs font-medium text-yellow-400"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      {zones.length === 1
        ? `${zones[0]} degraded`
        : `${zones.length} zones degraded`}
    </span>
  );
}
