"use client";

import { useEffect } from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";

import { useIngestProgress } from "@/hooks/use-ingest-progress";
import type { StageInfo, IngestStageStatus } from "@/types/api";

interface IngestProgressToastProps {
  ticker: string;
  onComplete?: () => void;
}

const STAGES = [
  "prices",
  "signals",
  "fundamentals",
  "forecast",
  "news",
  "sentiment",
  "convergence",
] as const;

function StageIcon({ status }: { status: IngestStageStatus }) {
  if (status === "fresh") return <Check className="h-3 w-3 text-green-500" />;
  if (status === "pending" || status === "missing")
    return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
  return <AlertCircle className="h-3 w-3 text-yellow-500" />;
}

export function IngestProgressToast({ ticker, onComplete }: IngestProgressToastProps) {
  const { data } = useIngestProgress(ticker, true);

  useEffect(() => {
    if (data?.overall_status === "ready") {
      const t = setTimeout(() => onComplete?.(), 5000);
      return () => clearTimeout(t);
    }
  }, [data?.overall_status, onComplete]);

  if (!data) return <div className="text-sm">Starting ingest for {ticker}…</div>;

  return (
    <div className="space-y-2 text-sm" data-testid="ingest-progress-toast">
      <div className="font-medium">
        {ticker} — {data.completion_pct}% complete
      </div>
      <div className="space-y-1">
        {STAGES.map((stage) => {
          const info: StageInfo = data.stages[stage];
          return (
            <div key={stage} className="flex items-center gap-2">
              <StageIcon status={info.status} />
              <span className="text-xs capitalize">{stage}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
