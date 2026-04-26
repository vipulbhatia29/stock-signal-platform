"use client";

import { useState } from "react";
import { useAuditLog } from "@/hooks/use-admin-pipelines";

const ACTION_OPTIONS = [
  { value: "", label: "All Actions" },
  { value: "trigger_group", label: "Trigger Group" },
  { value: "trigger_task", label: "Trigger Task" },
  { value: "cache_clear", label: "Cache Clear" },
  { value: "cache_clear_all", label: "Cache Clear All" },
];

const PAGE_SIZE = 50;

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function formatMetadata(metadata: Record<string, unknown> | null): string {
  if (!metadata) return "—";
  if ("keys_deleted" in metadata) return `${metadata.keys_deleted} keys`;
  if ("failure_mode" in metadata) return `mode: ${metadata.failure_mode}`;
  return "—";
}

export function AuditLogTable() {
  const [action, setAction] = useState<string | undefined>(undefined);
  const [offset, setOffset] = useState(0);
  const { data, isLoading } = useAuditLog(action, PAGE_SIZE, offset);

  const total = data?.total ?? 0;
  const hasNext = offset + PAGE_SIZE < total;
  const hasPrev = offset > 0;

  return (
    <div className="rounded-xl bg-card border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium">Audit Log</h3>
        <select
          aria-label="Filter by action"
          value={action ?? ""}
          onChange={(e) => {
            setAction(e.target.value || undefined);
            setOffset(0);
          }}
          className="text-xs bg-card2 border border-border rounded px-2 py-1 text-foreground"
        >
          {ACTION_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p className="text-xs text-subtle">Loading...</p>
      ) : !data?.entries.length ? (
        <p className="text-xs text-subtle py-4 text-center">No audit log entries</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left text-subtle">
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2 pr-4">Action</th>
                  <th className="pb-2 pr-4">Target</th>
                  <th className="pb-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-mono text-subtle">
                      {formatRelativeTime(entry.created_at)}
                    </td>
                    <td className="py-2 pr-4">{entry.action}</td>
                    <td className="py-2 pr-4 font-mono">{entry.target ?? "—"}</td>
                    <td className="py-2 text-subtle">{formatMetadata(entry.metadata)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between mt-3 text-xs text-subtle">
            <span>{offset + 1}-{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={!hasPrev}
                className="px-2 py-1 rounded border border-border disabled:opacity-30"
              >
                Prev
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={!hasNext}
                className="px-2 py-1 rounded border border-border disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
