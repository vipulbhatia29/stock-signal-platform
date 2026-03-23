"use client";

import { cn } from "@/lib/utils";
import { useScorecard } from "@/hooks/use-forecasts";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import type { ScorecardResponse } from "@/types/api";

interface ScorecardModalProps {
  children: React.ReactNode;
}

function MetricRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "gain" | "loss" | "warn";
}) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-subtle">{label}</span>
      <span
        className={cn(
          "font-mono text-sm font-semibold",
          accent === "gain" && "text-gain",
          accent === "loss" && "text-loss",
          accent === "warn" && "text-warning",
          !accent && "text-foreground"
        )}
      >
        {value}
      </span>
    </div>
  );
}

function ScorecardContent({ scorecard }: { scorecard: ScorecardResponse }) {
  if (scorecard.total_outcomes === 0) {
    return (
      <div className="py-6 text-center text-sm text-subtle">
        No evaluated recommendations yet. Scorecard populates after the
        nightly pipeline evaluates past recommendations.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Overall metrics */}
      <div className="space-y-0.5">
        <MetricRow
          label="Overall Hit Rate"
          value={`${(scorecard.overall_hit_rate * 100).toFixed(1)}%`}
          accent={scorecard.overall_hit_rate >= 0.7 ? "gain" : "warn"}
        />
        <MetricRow
          label="Average Alpha"
          value={`${scorecard.avg_alpha >= 0 ? "+" : ""}${(scorecard.avg_alpha * 100).toFixed(2)}%`}
          accent={scorecard.avg_alpha >= 0 ? "gain" : "loss"}
        />
        <MetricRow
          label="Buy Hit Rate"
          value={`${(scorecard.buy_hit_rate * 100).toFixed(1)}%`}
        />
        <MetricRow
          label="Sell Hit Rate"
          value={`${(scorecard.sell_hit_rate * 100).toFixed(1)}%`}
        />
        <MetricRow
          label="Total Evaluations"
          value={String(scorecard.total_outcomes)}
        />
      </div>

      {/* Worst miss */}
      {scorecard.worst_miss_ticker && (
        <div className="rounded-lg border border-border bg-card2 p-3">
          <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle mb-1">
            Worst Miss
          </div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-sm text-foreground">
              {scorecard.worst_miss_ticker}
            </span>
            <span className="font-mono text-sm font-semibold text-loss">
              {(scorecard.worst_miss_pct * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      )}

      {/* Per-horizon breakdown */}
      {scorecard.by_horizon.length > 0 && (
        <div>
          <div className="text-[9px] font-semibold uppercase tracking-[0.08em] text-subtle mb-2">
            By Horizon
          </div>
          <div className="grid grid-cols-3 gap-2">
            {scorecard.by_horizon.map((h) => (
              <div
                key={h.horizon_days}
                className="rounded-lg border border-border bg-card/50 p-2.5 text-center"
              >
                <div className="text-[9px] font-semibold uppercase text-subtle">
                  {h.horizon_days}d
                </div>
                <div className="font-mono text-lg font-bold text-foreground leading-none mt-1">
                  {(h.hit_rate * 100).toFixed(0)}%
                </div>
                <div className="text-[9px] text-subtle mt-0.5">
                  {h.correct}/{h.total}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ScorecardModal({ children }: ScorecardModalProps) {
  const { data: scorecard, isLoading } = useScorecard();

  return (
    <Dialog>
      <DialogTrigger render={<span className="cursor-pointer">{children}</span>} />
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Recommendation Scorecard</DialogTitle>
          <DialogDescription>
            How accurate your past BUY/SELL recommendations have been.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3 py-4">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-6 rounded bg-muted animate-pulse"
              />
            ))}
          </div>
        ) : scorecard ? (
          <ScorecardContent scorecard={scorecard} />
        ) : (
          <div className="py-6 text-center text-sm text-subtle">
            Failed to load scorecard data.
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
