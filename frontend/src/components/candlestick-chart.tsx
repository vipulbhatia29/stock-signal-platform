"use client";

import { useRef, useEffect } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
} from "lightweight-charts";
import type { IChartApi } from "lightweight-charts";
import { useLightweightChartTheme } from "@/lib/lightweight-chart-theme";
import type { OHLCResponse } from "@/types/api";

interface CandlestickChartProps {
  data: OHLCResponse | undefined;
}

export function CandlestickChart({ data }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { theme, candleColors } = useLightweightChartTheme();

  useEffect(() => {
    if (!containerRef.current || !data || data.count === 0) return;

    const chart = createChart(containerRef.current, {
      ...theme,
      width: containerRef.current.clientWidth,
      height: 400,
      autoSize: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: candleColors.up,
      downColor: candleColors.down,
      borderUpColor: candleColors.up,
      borderDownColor: candleColors.down,
      wickUpColor: candleColors.up,
      wickDownColor: candleColors.down,
    });

    const candles = data.timestamps.map((ts, i) => ({
      time: ts.split("T")[0] as string,
      open: data.open[i],
      high: data.high[i],
      low: data.low[i],
      close: data.close[i],
    }));
    candleSeries.setData(candles);

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    const volumes = data.timestamps.map((ts, i) => ({
      time: ts.split("T")[0] as string,
      value: data.volume[i],
      color:
        data.close[i] >= data.open[i]
          ? `${candleColors.up}40`
          : `${candleColors.down}40`,
    }));
    volumeSeries.setData(volumes);

    chart.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, 400);
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, theme, candleColors]);

  if (!data) return null;

  return (
    <div
      ref={containerRef}
      data-testid="candlestick-container"
      className="w-full min-h-[400px]"
    />
  );
}
