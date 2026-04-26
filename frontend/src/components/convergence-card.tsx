"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useStockConvergence, useConvergenceHistory } from "@/hooks/use-convergence";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors } from "@/lib/chart-theme";
import { cn } from "@/lib/utils";
import type {
  ConvergenceLabelType,
  SignalDirectionDetail,
} from "@/types/api";

interface ConvergenceCardProps {
  ticker: string;
  enabled?: boolean;
}

const LABEL_CONFIG: Record<
  ConvergenceLabelType,
  { text: string; bg: string; fg: string; value: number }
> = {
  strong_bull: { text: "STRONG BULL", bg: "bg-green-900/60", fg: "text-green-400", value: 5 },
  weak_bull: { text: "WEAK BULL", bg: "bg-green-900/30", fg: "text-green-300", value: 4 },
  mixed: { text: "MIXED", bg: "bg-amber-900/30", fg: "text-amber-300", value: 3 },
  weak_bear: { text: "WEAK BEAR", bg: "bg-red-900/30", fg: "text-red-300", value: 2 },
  strong_bear: { text: "STRONG BEAR", bg: "bg-red-900/60", fg: "text-red-400", value: 1 },
};

const DIRECTION_ICON: Record<string, { icon: string; color: string }> = {
  bullish: { icon: "↑", color: "text-green-400" },
  bearish: { icon: "↓", color: "text-red-400" },
  neutral: { icon: "—", color: "text-muted-foreground" },
};

function SignalDirections({ signals }: { signals: SignalDirectionDetail[] }) {
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
      {signals.map((s) => {
        const dir = DIRECTION_ICON[s.direction] ?? DIRECTION_ICON.neutral;
        return (
          <span key={s.signal} className="whitespace-nowrap">
            <span className="text-muted-foreground uppercase">{s.signal}</span>
            <span className={cn("ml-0.5 font-medium", dir.color)}>{dir.icon}</span>
          </span>
        );
      })}
    </div>
  );
}

export function ConvergenceCard({ ticker, enabled = true }: ConvergenceCardProps) {
  const {
    data: convergence,
    isLoading,
    isError,
    refetch,
  } = useStockConvergence(ticker, enabled);
  const { data: history } = useConvergenceHistory(ticker, 30, enabled);
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SectionHeading>Signal Convergence</SectionHeading>
        <Skeleton className="h-16 rounded-lg" />
        <Skeleton className="h-[80px] rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <SectionHeading>Signal Convergence</SectionHeading>
        <ErrorState error="Failed to load convergence data" onRetry={refetch} />
      </div>
    );
  }

  if (!convergence) return null;

  const label = LABEL_CONFIG[convergence.convergence_label] ?? LABEL_CONFIG.mixed;
  const { divergence } = convergence;

  const chartData = history?.data.map((row) => ({
    date: row.date,
    value: LABEL_CONFIG[row.convergence_label]?.value ?? 3,
  }));

  return (
    <div className="space-y-3">
      <SectionHeading>Signal Convergence</SectionHeading>

      {/* Label + alignment */}
      <div className="flex items-center gap-3">
        <span className={cn("rounded-md px-3 py-1.5 text-sm font-bold", label.bg, label.fg)}>
          {label.text}
        </span>
        <div className="space-y-1">
          <p className="text-sm text-foreground">
            {convergence.signals_aligned} of {convergence.signals.length} signals{" "}
            {convergence.convergence_label.includes("bull") ? "bullish" : convergence.convergence_label.includes("bear") ? "bearish" : "aligned"}
          </p>
          <SignalDirections signals={convergence.signals} />
        </div>
      </div>

      {/* Divergence alert */}
      {divergence.is_divergent && (
        <div className="rounded-md border border-amber-800/50 bg-amber-950/30 px-3 py-2 text-sm">
          <span className="font-semibold text-amber-400">⚠ Divergence: </span>
          <span className="text-amber-200/80">
            {divergence.forecast_direction} forecast vs {divergence.technical_majority} technicals.
            {divergence.historical_hit_rate != null && (
              <> Historically, forecast was right {Math.round(divergence.historical_hit_rate * 100)}% of the time (n={divergence.sample_count}).</>
            )}
          </span>
        </div>
      )}

      {/* Rationale */}
      {convergence.rationale && (
        <p className="text-xs text-muted-foreground">{convergence.rationale}</p>
      )}

      {/* History chart */}
      {chartData && chartData.length > 1 && (
        <ResponsiveContainer width="100%" height={80}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="convergenceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={colors.gain} stopOpacity={0.3} />
                <stop offset="95%" stopColor={colors.gain} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" hide />
            <YAxis domain={[1, 5]} hide />
            <Tooltip
              content={({ active, payload }) => {
                if (!payload?.[0]) return null;
                const val = payload[0].value as number;
                const labelName = Object.values(LABEL_CONFIG).find((l) => l.value === val)?.text ?? "MIXED";
                return (
                  <ChartTooltip
                    active={active}
                    label={String(payload[0].payload.date)}
                    items={[{ name: "Convergence", value: labelName, color: colors.gain }]}
                  />
                );
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={colors.gain}
              fill="url(#convergenceGradient)"
              strokeWidth={1.5}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
