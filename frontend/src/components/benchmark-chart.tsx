"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatChartDate, formatPctChange } from "@/lib/format";
import type { BenchmarkDataPoint } from "@/hooks/use-stocks";

// Map series index to chart color key
const SERIES_COLOR_KEYS = ["price", "chart1", "chart2"] as const;

interface BenchmarkChartProps {
  data: BenchmarkDataPoint[] | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
  seriesNames: string[];
}

export function BenchmarkChart({
  data,
  isLoading,
  isError,
  onRetry,
  seriesNames,
}: BenchmarkChartProps) {
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>Benchmark Comparison</SectionHeading>
        <Skeleton className="h-[250px] w-full sm:h-[350px]" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <SectionHeading>Benchmark Comparison</SectionHeading>
        <ErrorState error="Failed to load benchmark data" onRetry={onRetry} />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="space-y-4">
        <SectionHeading>Benchmark Comparison</SectionHeading>
        <p className="text-sm text-muted-foreground">No benchmark data available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeading>Benchmark Comparison</SectionHeading>
      <ResponsiveContainer width="100%" height="100%" minHeight={250} className="sm:min-h-[350px]">
        <LineChart data={data}>
          <CartesianGrid {...CHART_STYLE.grid} />
          <XAxis
            dataKey="date"
            tickFormatter={formatChartDate}
            interval="preserveStartEnd"
            minTickGap={60}
            {...CHART_STYLE.axis}
          />
          <YAxis
            tickFormatter={(v: number) => formatPctChange(v)}
            width={65}
            {...CHART_STYLE.axis}
          />
          <Tooltip
            cursor={CHART_STYLE.tooltip.cursor}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as BenchmarkDataPoint;
              return (
                <ChartTooltip
                  active={active}
                  label={formatChartDate(d.date)}
                  items={seriesNames.map((name, i) => ({
                    name,
                    value: formatPctChange(
                      typeof d[name] === "number" ? d[name] : null
                    ),
                    color: colors[SERIES_COLOR_KEYS[i] ?? "chart3"],
                  }))}
                />
              );
            }}
          />
          <Legend
            verticalAlign="top"
            height={30}
            wrapperStyle={{ fontSize: "12px" }}
          />
          {seriesNames.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={colors[SERIES_COLOR_KEYS[i] ?? "chart3"]}
              strokeWidth={i === 0 ? 2 : 1.5}
              dot={false}
              strokeDasharray={i === 0 ? undefined : "5 3"}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
