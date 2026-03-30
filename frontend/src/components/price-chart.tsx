"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import {
  ComposedChart,
  Area,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { usePrices, useOHLC } from "@/hooks/use-stocks";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionHeading } from "@/components/section-heading";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors, CHART_STYLE } from "@/lib/chart-theme";
import { formatCurrency, formatVolume, formatChartDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PricePeriod } from "@/types/api";

const DynamicCandlestick = dynamic(
  () =>
    import("@/components/candlestick-chart").then((m) => m.CandlestickChart),
  { ssr: false, loading: () => <Skeleton className="h-[400px] w-full" /> }
);

type ChartMode = "line" | "candle";

const PERIODS: { value: PricePeriod; label: string }[] = [
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "5y", label: "5Y" },
];

interface PriceChartProps {
  ticker: string;
  period: PricePeriod;
  onPeriodChange: (p: PricePeriod) => void;
}

export function PriceChart({ ticker, period, onPeriodChange }: PriceChartProps) {
  const [chartMode, setChartMode] = useState<ChartMode>("line");
  const { data: prices, isLoading: pricesLoading } = usePrices(ticker, period);
  const { data: ohlc, isLoading: ohlcLoading } = useOHLC(
    ticker,
    period,
    chartMode === "candle"
  );
  const colors = useChartColors();

  const trendColor =
    prices && prices.length >= 2
      ? prices[prices.length - 1].close > prices[0].close
        ? colors.gain
        : prices[prices.length - 1].close < prices[0].close
          ? colors.loss
          : colors.price
      : colors.price;

  const modeToggle = (
    <div className="flex gap-1">
      {(["line", "candle"] as const).map((mode) => (
        <Button
          key={mode}
          variant={chartMode === mode ? "secondary" : "ghost"}
          size="sm"
          className="h-7 px-2.5 text-xs capitalize"
          onClick={() => setChartMode(mode)}
        >
          {mode}
        </Button>
      ))}
    </div>
  );

  const periodSelector = (
    <div className="flex gap-1">
      {PERIODS.map((p) => (
        <Button
          key={p.value}
          variant={period === p.value ? "secondary" : "ghost"}
          size="sm"
          className={cn("h-7 px-2.5 text-xs")}
          onClick={() => onPeriodChange(p.value)}
        >
          {p.label}
        </Button>
      ))}
    </div>
  );

  const actions = (
    <div className="flex items-center gap-3">
      {modeToggle}
      <div className="h-4 w-px bg-border" />
      {periodSelector}
    </div>
  );

  const isLoading = chartMode === "line" ? pricesLoading : ohlcLoading;

  return (
    <div>
      <SectionHeading action={actions}>Price History</SectionHeading>

      {isLoading ? (
        <Skeleton className="h-[250px] w-full sm:h-[400px]" />
      ) : chartMode === "candle" ? (
        <DynamicCandlestick data={ohlc} />
      ) : (
        <ResponsiveContainer width="100%" height="100%" minHeight={250} className="sm:min-h-[400px]">
          <ComposedChart
            data={prices}
            role="img"
            aria-label={`${ticker} price history chart`}
          >
            <defs>
              <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={trendColor} stopOpacity={0.3} />
                <stop offset="95%" stopColor={trendColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...CHART_STYLE.grid} />
            <XAxis
              dataKey="time"
              tickFormatter={formatChartDate}
              interval="preserveStartEnd"
              minTickGap={60}
              {...CHART_STYLE.axis}
            />
            <YAxis
              yAxisId="price"
              orientation="left"
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
              width={60}
              domain={["auto", "auto"]}
              {...CHART_STYLE.axis}
            />
            <YAxis
              yAxisId="volume"
              orientation="right"
              tickFormatter={formatVolume}
              width={50}
              {...CHART_STYLE.axis}
            />
            <Tooltip
              cursor={CHART_STYLE.tooltip.cursor}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const d = payload[0].payload as {
                  time: string;
                  close: number;
                  volume: number;
                };
                return (
                  <ChartTooltip
                    active={active}
                    label={formatChartDate(d.time)}
                    items={[
                      { name: "Price", value: formatCurrency(d.close), color: colors.price },
                      { name: "Volume", value: formatVolume(d.volume), color: colors.volume },
                    ]}
                  />
                );
              }}
            />
            <Area
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke={colors.price}
              fill="url(#priceGradient)"
              strokeWidth={2}
            />
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill={colors.volume}
              opacity={0.4}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
