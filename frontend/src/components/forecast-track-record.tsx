"use client";

import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useForecastTrackRecord } from "@/hooks/use-forecasts";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatChartDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface ForecastTrackRecordProps {
  ticker: string;
  enabled?: boolean;
}

function KpiTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: "green" | "amber" | "red" | "neutral";
}) {
  const accentColor = {
    green: "text-green-400",
    amber: "text-amber-400",
    red: "text-red-400",
    neutral: "text-foreground",
  }[accent];

  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("text-sm font-semibold tabular-nums", accentColor)}>{value}</p>
    </div>
  );
}

function rateAccent(value: number, greenThreshold: number, amberThreshold: number): "green" | "amber" | "red" {
  if (value >= greenThreshold) return "green";
  if (value >= amberThreshold) return "amber";
  return "red";
}

function errorAccent(value: number): "green" | "amber" | "red" {
  if (value < 5) return "green";
  if (value < 10) return "amber";
  return "red";
}

export function ForecastTrackRecord({ ticker, enabled = true }: ForecastTrackRecordProps) {
  const { data, isLoading, isError, refetch } = useForecastTrackRecord(
    enabled ? ticker : null,
  );
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SectionHeading>Forecast Track Record</SectionHeading>
        <Skeleton className="h-[120px] rounded-lg" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <SectionHeading>Forecast Track Record</SectionHeading>
        <ErrorState error="Failed to load track record" onRetry={refetch} />
      </div>
    );
  }

  if (!data || data.summary.total_evaluated === 0) {
    return (
      <div className="space-y-3">
        <SectionHeading>Forecast Track Record</SectionHeading>
        <div className="rounded-lg border border-border bg-card px-4 py-6 text-center">
          <p className="text-sm text-muted-foreground">
            No evaluated forecasts yet. Track record builds as predictions mature
            (typically 30–90 days after first forecast).
          </p>
        </div>
      </div>
    );
  }

  const { evaluations, summary } = data;

  const chartData = evaluations.map((e) => ({
    date: e.target_date,
    predicted: e.expected_return_pct,
    actual: e.actual_return_pct,
    lower: e.return_lower_pct,
    upper: e.return_upper_pct,
    bandWidth: e.return_upper_pct - e.return_lower_pct,
  }));

  return (
    <div className="space-y-3">
      <SectionHeading>Forecast Track Record</SectionHeading>

      {/* Predicted vs Actual chart */}
      <ResponsiveContainer width="100%" height={120}>
        <ComposedChart data={chartData}>
          <CartesianGrid {...CHART_STYLE.grid} />
          <XAxis
            dataKey="date"
            tickFormatter={formatChartDate}
            interval="preserveStartEnd"
            minTickGap={60}
            {...CHART_STYLE.axis}
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}
            {...CHART_STYLE.axis}
            width={58}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload;
              return (
                <ChartTooltip
                  active={active}
                  label={d.date}
                  items={[
                    { name: "Predicted", value: `${d.predicted > 0 ? "+" : ""}${d.predicted.toFixed(1)}%`, color: colors.chart1 },
                    { name: "Actual", value: d.actual != null ? `${d.actual > 0 ? "+" : ""}${d.actual.toFixed(1)}%` : "Pending", color: colors.price },
                    { name: "CI Band", value: `${d.lower.toFixed(1)}% to ${d.upper.toFixed(1)}%`, color: "#6b7280" },
                  ]}
                />
              );
            }}
          />
          {/* Confidence interval band — stacked: invisible lower base + visible band */}
          <Area
            type="monotone"
            dataKey="lower"
            stackId="ci"
            stroke="none"
            fill="transparent"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="bandWidth"
            stackId="ci"
            stroke="none"
            fill="#6b728020"
            isAnimationActive={false}
          />
          {/* Predicted line */}
          <Line
            type="monotone"
            dataKey="predicted"
            stroke={colors.chart1}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          {/* Actual line */}
          <Line
            type="monotone"
            dataKey="actual"
            stroke={colors.price}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Summary KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <KpiTile label="Forecasts" value={String(summary.total_evaluated)} accent="neutral" />
        <KpiTile
          label="Direction Hit"
          value={`${Math.round(summary.direction_hit_rate * 100)}%`}
          accent={rateAccent(summary.direction_hit_rate, 0.7, 0.5)}
        />
        <KpiTile
          label="Avg Error"
          value={`${(summary.avg_error_pct * 100).toFixed(1)}%`}
          accent={errorAccent(summary.avg_error_pct * 100)}
        />
        <KpiTile
          label="CI Hit"
          value={`${Math.round(summary.ci_containment_rate * 100)}%`}
          accent={rateAccent(summary.ci_containment_rate, 0.8, 0.6)}
        />
      </div>
    </div>
  );
}
