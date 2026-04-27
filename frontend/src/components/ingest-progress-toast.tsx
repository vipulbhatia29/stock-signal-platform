"use client";

import { useEffect } from "react";
import { Check, Loader2, AlertCircle, X } from "lucide-react";

import { useIngestProgress } from "@/hooks/use-ingest-progress";
import { cn } from "@/lib/utils";
import type { StageInfo, IngestStageStatus } from "@/types/api";

interface IngestProgressToastProps {
  ticker: string;
  onComplete?: () => void;
}

/** Stages that run during on-demand ingest (synchronous). */
const INGEST_STAGES = ["prices", "signals", "fundamentals"] as const;

/** Stages that only run during nightly pipeline. */
const NIGHTLY_STAGES = ["forecast", "news", "sentiment", "convergence"] as const;

function StageIcon({ status }: { status: IngestStageStatus }) {
  if (status === "fresh") return <Check className="h-3 w-3 text-gain" />;
  if (status === "pending" || status === "missing")
    return <Loader2 className="h-3 w-3 animate-spin text-primary" />;
  return <AlertCircle className="h-3 w-3 text-warning" />;
}

export function IngestProgressToast({ ticker, onComplete }: IngestProgressToastProps) {
  const { data } = useIngestProgress(ticker, true);

  // "Done" = the 3 ingest stages are fresh (ignore nightly stages)
  const ingestDone = data
    ? INGEST_STAGES.every((s) => data.stages[s]?.status === "fresh")
    : false;

  useEffect(() => {
    if (ingestDone) {
      const t = setTimeout(() => onComplete?.(), 3000);
      return () => clearTimeout(t);
    }
  }, [ingestDone, onComplete]);

  const freshCount = data
    ? INGEST_STAGES.filter((s) => data.stages[s]?.status === "fresh").length
    : 0;
  const pct = Math.round((freshCount / INGEST_STAGES.length) * 100);

  return (
    <div
      className="w-[280px] rounded-lg border border-border bg-card shadow-lg shadow-black/20 p-4"
      data-testid="ingest-progress-toast"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold">{ticker}</span>
          {ingestDone ? (
            <span className="rounded-full bg-gain/15 px-2 py-0.5 text-[9px] font-semibold text-gain">Ready</span>
          ) : (
            <span className="text-[10px] text-muted-foreground">{pct}%</span>
          )}
        </div>
        <button onClick={onComplete} className="text-muted-foreground hover:text-foreground transition-colors">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Progress bar */}
      <div className="h-1 w-full rounded-full bg-muted/30 mb-3">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            ingestDone ? "bg-gain" : "bg-primary",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Ingest stages */}
      {data ? (
        <div className="space-y-1">
          {INGEST_STAGES.map((stage) => {
            const info: StageInfo = data.stages[stage];
            return (
              <div key={stage} className="flex items-center gap-1.5">
                <StageIcon status={info.status} />
                <span className={cn(
                  "text-[10px] capitalize",
                  info.status === "fresh" ? "text-muted-foreground" : "text-foreground",
                )}>
                  {stage}
                </span>
              </div>
            );
          })}
          {ingestDone && (
            <p className="text-[9px] text-muted-foreground mt-2">
              Forecast & sentiment run overnight
            </p>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
          <span className="text-xs text-muted-foreground">Starting pipeline…</span>
        </div>
      )}
    </div>
  );
}
