"use client";

import { Fragment, useState, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { ChevronUp, ChevronDown, MessageSquare } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { useObservabilityQueries } from "@/hooks/use-observability";
import { formatMicroCurrency, formatDuration, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { QueryRowDetail } from "./query-row-detail";

const MAX_TOOL_BADGES = 3;

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-gdim text-gain",
  error: "bg-ldim text-loss",
  declined: "bg-wdim text-warning",
  timeout: "bg-muted text-muted-foreground",
};

interface Column {
  key: string;
  label: string;
  sortable: boolean;
  adminOnly?: boolean;
}

const COLUMNS: Column[] = [
  { key: "expand", label: "", sortable: false },
  { key: "timestamp", label: "Time", sortable: true },
  { key: "query_text", label: "Query", sortable: false },
  { key: "agent_type", label: "Agent", sortable: false },
  { key: "tools_used", label: "Tools", sortable: false },
  { key: "llm_calls", label: "LLM Calls", sortable: true },
  { key: "total_cost_usd", label: "Cost", sortable: true },
  { key: "duration_ms", label: "Duration", sortable: true },
  { key: "status", label: "Status", sortable: false },
  { key: "score", label: "Score", sortable: true, adminOnly: true },
];

export function QueryTable({ isAdmin }: { isAdmin: boolean }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const page = Number(searchParams.get("page") ?? "1");
  const sortBy = searchParams.get("sort") ?? "timestamp";
  const sortOrder = (searchParams.get("order") ?? "desc") as "asc" | "desc";
  const statusFilter = searchParams.get("status") ?? undefined;
  const costMin = searchParams.get("cost_min") ? Number(searchParams.get("cost_min")) : undefined;
  const costMax = searchParams.get("cost_max") ? Number(searchParams.get("cost_max")) : undefined;

  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useObservabilityQueries({
    page,
    sort_by: sortBy,
    sort_order: sortOrder,
    status: statusFilter,
    cost_min: costMin,
    cost_max: costMax,
  });

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const params = new URLSearchParams(searchParams.toString());
      Object.entries(updates).forEach(([k, v]) => {
        if (v === undefined) params.delete(k);
        else params.set(k, v);
      });
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [searchParams, router, pathname],
  );

  const handleSort = (col: string) => {
    if (col === sortBy) {
      updateParams({ order: sortOrder === "desc" ? "asc" : "desc" });
    } else {
      updateParams({ sort: col, order: "desc" });
    }
  };

  const handleRowClick = (queryId: string) => {
    setExpandedId((prev) => (prev === queryId ? null : queryId));
  };

  const visibleCols = COLUMNS.filter((c) => !c.adminOnly || isAdmin);
  const totalPages = data ? Math.ceil(data.total / (data.size || 25)) : 0;

  return (
    <section aria-label="Query History">
      <SectionHeading>Query History</SectionHeading>

      {/* Status filter pills + cost range */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {["all", "completed", "error", "declined", "timeout"].map((s) => (
          <button
            key={s}
            onClick={() => updateParams({ status: s === "all" ? undefined : s, page: "1" })}
            className={cn(
              "rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors",
              (s === "all" && !statusFilter) || statusFilter === s
                ? "bg-cdim text-cyan"
                : "bg-card2 text-muted-foreground hover:text-foreground",
            )}
          >
            {s}
          </button>
        ))}

        {/* Cost range inputs */}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-[9.5px] font-medium uppercase tracking-wider text-subtle">Cost</span>
          <input
            type="number"
            step="0.001"
            min="0"
            placeholder="Min"
            value={costMin ?? ""}
            onChange={(e) =>
              updateParams({
                cost_min: e.target.value || undefined,
                page: "1",
              })
            }
            className="w-20 rounded-md border border-border bg-card2 px-2 py-1 text-xs font-mono text-foreground placeholder:text-subtle focus:border-[var(--bhi)] focus:outline-none"
          />
          <span className="text-subtle">&ndash;</span>
          <input
            type="number"
            step="0.001"
            min="0"
            placeholder="Max"
            value={costMax ?? ""}
            onChange={(e) =>
              updateParams({
                cost_max: e.target.value || undefined,
                page: "1",
              })
            }
            className="w-20 rounded-md border border-border bg-card2 px-2 py-1 text-xs font-mono text-foreground placeholder:text-subtle focus:border-[var(--bhi)] focus:outline-none"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No queries yet"
          description="Try asking the AI agent a question!"
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-card2">
                  {visibleCols.map((col) => (
                    <th
                      key={col.key}
                      className={cn(
                        "px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle",
                        col.key === "expand" && "w-8 px-2",
                      )}
                      aria-sort={col.sortable ? (col.key === sortBy ? (sortOrder === "asc" ? "ascending" : "descending") : "none") : undefined}
                    >
                      {col.sortable ? (
                        <button
                          className="inline-flex items-center gap-1 hover:text-foreground"
                          onClick={() => handleSort(col.key)}
                        >
                          {col.label}
                          {col.key === sortBy && (
                            sortOrder === "asc"
                              ? <ChevronUp className="h-3 w-3" />
                              : <ChevronDown className="h-3 w-3" />
                          )}
                        </button>
                      ) : (
                        col.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <Fragment key={row.query_id}>
                    <tr
                      role="button"
                      tabIndex={0}
                      aria-expanded={expandedId === row.query_id}
                      onClick={() => handleRowClick(row.query_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          handleRowClick(row.query_id);
                        }
                      }}
                      className="cursor-pointer border-t border-border/40 transition-colors hover:bg-hov"
                    >
                      <td className="px-2 py-2 w-8">
                        <ChevronDown
                          className={cn(
                            "h-3.5 w-3.5 transition-transform",
                            expandedId === row.query_id
                              ? "text-cyan"
                              : "text-subtle rotate-[-90deg]",
                          )}
                        />
                      </td>
                      <td className="px-3 py-2 text-muted-foreground text-xs whitespace-nowrap">
                        {formatRelativeTime(row.timestamp)}
                      </td>
                      <td className="px-3 py-2 max-w-[200px] truncate text-foreground">
                        {row.query_text}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted-foreground">
                        {row.agent_type}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {row.tools_used.slice(0, MAX_TOOL_BADGES).map((t) => (
                            <span key={t} className="rounded-full bg-cdim px-2 py-0.5 text-[10px] font-medium text-cyan">
                              {t}
                            </span>
                          ))}
                          {row.tools_used.length > MAX_TOOL_BADGES && (
                            <span className="rounded-full bg-card2 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                              +{row.tools_used.length - MAX_TOOL_BADGES}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                        {row.llm_calls}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-foreground">
                        {formatMicroCurrency(row.total_cost_usd)}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                        {formatDuration(row.duration_ms)}
                      </td>
                      <td className="px-3 py-2">
                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", STATUS_STYLES[row.status] ?? "bg-muted text-muted-foreground")}>
                          {row.status}
                        </span>
                      </td>
                      {isAdmin && (
                        <td className="px-3 py-2 font-mono text-xs">
                          {row.score !== null ? (
                            <span className={cn(row.score >= 8 ? "text-gain" : row.score >= 5 ? "text-warning" : "text-loss")}>
                              {row.score.toFixed(1)}
                            </span>
                          ) : (
                            <span className="text-subtle">---</span>
                          )}
                        </td>
                      )}
                    </tr>
                    {expandedId === row.query_id && (
                      <tr>
                        <td colSpan={visibleCols.length} className="bg-card2/50 px-4 py-3">
                          <QueryRowDetail
                            queryId={row.query_id}
                            queryText={row.query_text}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Page {data.page} of {totalPages} ({data.total} queries)
              </span>
              <div className="flex gap-2">
                <button
                  disabled={data.page <= 1}
                  onClick={() => updateParams({ page: String(data.page - 1) })}
                  className="rounded-lg bg-card2 px-3 py-1.5 transition-colors hover:bg-hov disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  disabled={data.page >= totalPages}
                  onClick={() => updateParams({ page: String(data.page + 1) })}
                  className="rounded-lg bg-card2 px-3 py-1.5 transition-colors hover:bg-hov disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
