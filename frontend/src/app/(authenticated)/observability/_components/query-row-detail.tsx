"use client";

import { ExternalLink } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useQueryDetail } from "@/hooks/use-observability";
import { formatMicroCurrency, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

const TYPE_TAG_STYLES: Record<string, string> = {
  llm: "bg-card2 text-[var(--chart-3)]",
  db: "bg-cdim text-cyan",
  external: "bg-wdim text-warning",
};

interface Props {
  queryId: string;
  queryText: string;
}

export function QueryRowDetail({ queryId, queryText }: Props) {
  const { data: detail, isLoading, isError } = useQueryDetail(queryId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg bg-card2" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-loss">
        Failed to load query details. Please try again.
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="space-y-3">
      {/* Full query text */}
      <p className="text-sm text-foreground">{detail.query_text || queryText}</p>

      {/* Steps timeline */}
      <div className="space-y-2">
        {detail.steps.map((step) => (
          <div
            key={step.step_number}
            className="flex items-start gap-3 rounded-lg border border-border/30 bg-card p-3"
          >
            {/* Step number */}
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-card2 text-[10px] font-bold text-muted-foreground">
              {step.step_number}
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {/* Action name */}
                <span className="font-mono text-xs font-medium text-foreground">
                  {step.action}
                </span>

                {/* Type tag */}
                <span className={cn("rounded-full px-2 py-0.5 text-[9px] font-semibold uppercase", TYPE_TAG_STYLES[step.type_tag] ?? "bg-muted text-muted-foreground")}>
                  {step.type_tag}
                </span>

                {/* Cache hit */}
                {step.cache_hit && (
                  <span className="rounded-full bg-gdim px-2 py-0.5 text-[9px] font-semibold text-gain">
                    cached
                  </span>
                )}
              </div>

              {/* Summaries */}
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
                {step.input_summary && <span>In: {step.input_summary}</span>}
                {step.output_summary && <span>Out: {step.output_summary}</span>}
                {step.latency_ms != null && <span>{formatDuration(step.latency_ms)}</span>}
                {step.cost_usd != null && <span>{formatMicroCurrency(step.cost_usd)}</span>}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Langfuse link */}
      {detail.langfuse_trace_url && (
        <a
          href={detail.langfuse_trace_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-card2 px-3 py-1.5 text-xs font-medium text-cyan transition-colors hover:bg-hov"
        >
          <ExternalLink className="h-3 w-3" />
          View in Langfuse
        </a>
      )}
    </div>
  );
}
