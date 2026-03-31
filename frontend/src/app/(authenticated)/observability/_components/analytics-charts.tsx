"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { BarChart3 } from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  BarChart,
  Line,
  Bar,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { EmptyState } from "@/components/empty-state";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { useObservabilityGrouped } from "@/hooks/use-observability";
import { formatChartDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface DimensionTab {
  key: string;
  label: string;
  adminOnly?: boolean;
}

const DIMENSIONS: DimensionTab[] = [
  { key: "date", label: "Over Time" },
  { key: "model", label: "By Model" },
  { key: "provider", label: "By Provider" },
  { key: "agent_type", label: "By Agent" },
  { key: "status", label: "By Status" },
  { key: "tool_name", label: "By Tool" },
  { key: "user", label: "By User", adminOnly: true },
  { key: "intent_category", label: "By Intent", adminOnly: true },
];

const BUCKETS = ["day", "week", "month"] as const;
const RANGES = ["7d", "30d", "90d"] as const;
const RANGE_DAYS: Record<string, number> = { "7d": 7, "30d": 30, "90d": 90 };

export function AnalyticsCharts({ isAdmin }: { isAdmin: boolean }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const colors = useChartColors();

  const dimension = searchParams.get("dim") ?? "date";
  const bucket = (searchParams.get("bucket") ?? "day") as (typeof BUCKETS)[number];
  const range = (searchParams.get("range") ?? "30d") as (typeof RANGES)[number];

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

  const dateFrom = useMemo(() => {
    const ms = RANGE_DAYS[range] * 86_400_000;
    return new Date(new Date().getTime() - ms).toISOString();
  }, [range]);

  const visibleDims = DIMENSIONS.filter((d) => !d.adminOnly || isAdmin);

  // Reset dimension if it's admin-only and user is not admin
  const activeDimension = DIMENSIONS.find(d => d.key === dimension && d.adminOnly && !isAdmin)
    ? "date"
    : dimension;

  const { data, isLoading } = useObservabilityGrouped({
    group_by: activeDimension,
    bucket: activeDimension === "date" ? bucket : undefined,
    date_from: dateFrom,
  });

  const isDateDim = activeDimension === "date";

  const chartData = (data?.groups ?? []).map((g) => ({
    ...g,
    label: isDateDim ? formatChartDate(g.key) : g.key,
  }));

  return (
    <section aria-label="Analytics">
      <SectionHeading>Usage Analytics</SectionHeading>

      {/* Dimension tabs */}
      <div className="mb-3 flex flex-wrap gap-2">
        {visibleDims.map((d) => (
          <button
            key={d.key}
            onClick={() => updateParams({ dim: d.key })}
            className={cn(
              "rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors",
              activeDimension === d.key
                ? "bg-cdim text-cyan"
                : "bg-card2 text-muted-foreground hover:text-foreground",
            )}
          >
            {d.label}
          </button>
        ))}
      </div>

      {/* Bucket + Range selectors */}
      <div className="mb-3 flex items-center justify-between">
        {/* Left: bucket selector (only for date) */}
        {isDateDim ? (
          <div className="flex gap-1.5">
            {BUCKETS.map((b) => (
              <button
                key={b}
                onClick={() => updateParams({ bucket: b })}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[10px] font-medium capitalize transition-colors",
                  bucket === b
                    ? "bg-card2 text-foreground"
                    : "text-subtle hover:text-muted-foreground",
                )}
              >
                {b}
              </button>
            ))}
          </div>
        ) : (
          <div />
        )}

        {/* Right: range selector */}
        <div className="flex gap-1.5">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => updateParams({ range: r })}
              className={cn(
                "rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
                range === r
                  ? "bg-card2 text-foreground"
                  : "text-subtle hover:text-muted-foreground",
              )}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-[260px] w-full rounded-lg bg-card2" />
      ) : !chartData.length ? (
        <div className="h-[260px]">
          <EmptyState
            icon={BarChart3}
            title="Not enough data"
            description="Not enough data to show trends"
          />
        </div>
      ) : isDateDim ? (
        <div className="rounded-lg border border-border bg-card p-4">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData}>
              <CartesianGrid {...CHART_STYLE.grid} />
              <XAxis dataKey="label" {...CHART_STYLE.axis} />
              <YAxis
                yAxisId="cost"
                orientation="left"
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                {...CHART_STYLE.axis}
              />
              <YAxis
                yAxisId="latency"
                orientation="right"
                tickFormatter={(v: number) => `${Math.round(v)}ms`}
                {...CHART_STYLE.axis}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                }}
                labelStyle={{ color: "var(--foreground)" }}
              />
              <Area
                yAxisId="cost"
                dataKey="total_cost_usd"
                stroke={colors.price}
                fill={colors.price}
                fillOpacity={0.1}
                name="Cost"
              />
              <Line
                yAxisId="latency"
                dataKey="avg_latency_ms"
                stroke={colors.sma200}
                dot={false}
                name="Avg Latency"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card p-4">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={chartData}
              layout={activeDimension === "tool_name" ? "vertical" : "horizontal"}
            >
              <CartesianGrid {...CHART_STYLE.grid} />
              {activeDimension === "tool_name" ? (
                <>
                  <YAxis
                    dataKey="label"
                    type="category"
                    width={120}
                    {...CHART_STYLE.axis}
                  />
                  <XAxis type="number" {...CHART_STYLE.axis} />
                </>
              ) : (
                <>
                  <XAxis dataKey="label" {...CHART_STYLE.axis} />
                  <YAxis {...CHART_STYLE.axis} />
                </>
              )}
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                }}
                labelStyle={{ color: "var(--foreground)" }}
              />
              <Bar
                dataKey="query_count"
                fill={colors.price}
                name="Queries"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
