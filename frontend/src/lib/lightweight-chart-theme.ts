"use client";

import { useState, useEffect } from "react";
import { CSS_VARS } from "@/lib/design-tokens";
import type { ChartOptions, DeepPartial } from "lightweight-charts";

function readCssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

function resolveTheme(): DeepPartial<ChartOptions> {
  const bg = readCssVar(CSS_VARS.card) || "#0a0e1a";
  const fg = readCssVar(CSS_VARS.foreground) || "#e2e8f0";
  const border = readCssVar(CSS_VARS.border) || "#1e293b";

  return {
    layout: {
      background: { color: bg },
      textColor: fg,
      fontFamily: "var(--font-sora), system-ui, sans-serif",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: border, style: 3 }, // dotted
      horzLines: { color: border, style: 3 },
    },
    crosshair: {
      vertLine: { color: fg, width: 1, style: 2 },
      horzLine: { color: fg, width: 1, style: 2 },
    },
    rightPriceScale: {
      borderColor: border,
    },
    timeScale: {
      borderColor: border,
    },
  };
}

export interface LightweightChartColors {
  up: string;
  down: string;
}

function resolveColors(): LightweightChartColors {
  return {
    up: readCssVar(CSS_VARS.gain) || "#22c55e",
    down: readCssVar(CSS_VARS.loss) || "#ef4444",
  };
}

export function useLightweightChartTheme() {
  const [theme, setTheme] = useState<DeepPartial<ChartOptions>>(() =>
    resolveTheme()
  );
  const [candleColors, setCandleColors] = useState<LightweightChartColors>(() =>
    resolveColors()
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setTheme(resolveTheme());
      setCandleColors(resolveColors());
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return { theme, candleColors };
}
