/** Shared constants and utilities for the observability admin dashboard. */

/** Format an ISO timestamp as a relative time string. */
export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) {
    const secs = Math.floor(diff / 1000);
    return secs < 1 ? "just now" : `${secs}s ago`;
  }
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Consistent layer colors used across Zone 2 and Zone 3. */
export const LAYER_COLORS: Record<string, string> = {
  http: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  db: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  cache: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  external_api: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  celery: "bg-pink-500/10 text-pink-400 border-pink-500/20",
  agent: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  frontend: "bg-teal-500/10 text-teal-400 border-teal-500/20",
  tool: "bg-amber-500/10 text-amber-400 border-amber-500/20",
};

/** Human-readable labels for layer keys. */
export const LAYER_LABELS: Record<string, string> = {
  http: "HTTP",
  db: "Database",
  cache: "Cache",
  external_api: "External API",
  celery: "Celery",
  agent: "Agent",
  frontend: "Frontend",
  tool: "Tool",
};

/** Consistent severity badge colors. */
export const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-500/10 text-red-500 border-red-500/20",
  error: "bg-orange-500/10 text-orange-500 border-orange-500/20",
  warning: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  info: "bg-blue-500/10 text-blue-500 border-blue-500/20",
};
