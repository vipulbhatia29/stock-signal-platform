"use client";

// Recharts theme constants and a hook to read CSS variables at runtime.
// Recharts requires literal color strings — it cannot resolve CSS variables.
// useChartColors() uses getComputedStyle to bridge this gap.

import { useEffect, useState } from "react";
import { CSS_VARS } from "@/lib/design-tokens";

function readCssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

export interface ChartColors {
  price: string;
  volume: string;
  sma50: string;
  sma200: string;
  rsi: string;
  chart1: string;
  chart2: string;
  chart3: string;
}

function resolveChartColors(): ChartColors {
  return {
    price: readCssVar(CSS_VARS.chartPrice),
    volume: readCssVar(CSS_VARS.chartVolume),
    sma50: readCssVar(CSS_VARS.chartSma50),
    sma200: readCssVar(CSS_VARS.chartSma200),
    rsi: readCssVar(CSS_VARS.chartRsi),
    chart1: readCssVar(CSS_VARS.chart1),
    chart2: readCssVar(CSS_VARS.chart2),
    chart3: readCssVar(CSS_VARS.chart3),
  };
}

// Returns chart colors that update when the theme changes (dark/light toggle).
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(() => resolveChartColors());

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setColors(resolveChartColors());
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return colors;
}

// Shared Recharts style constants — use across all charts for consistency.
export const CHART_STYLE = {
  grid: {
    strokeDasharray: "3 3" as const,
    className: "stroke-border/50",
  },
  axis: {
    tick: { fontSize: 11 },
    className: "text-muted-foreground",
  },
  tooltip: {
    cursor: { strokeDasharray: "4 2", stroke: "oklch(0.556 0 0)" },
  },
} as const;
