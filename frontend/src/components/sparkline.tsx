"use client";

// Sparkline — tiny inline line chart with no axes, grid, tooltip, or padding.
// Pure data ink. Used in screener tables and watchlist cards.

import { useEffect, useState } from "react";
import { LineChart, Line } from "recharts";
import { CSS_VARS } from "@/lib/design-tokens";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  sentiment?: "bullish" | "bearish" | "neutral";
}

function readCssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function resolveColor(sentiment: "bullish" | "bearish" | "neutral"): string {
  if (sentiment === "bullish") return readCssVar(CSS_VARS.gain);
  if (sentiment === "bearish") return readCssVar(CSS_VARS.loss);
  return readCssVar(CSS_VARS.neutralSignal);
}

function useSparklineColor(sentiment: "bullish" | "bearish" | "neutral"): string {
  const [color, setColor] = useState(() => resolveColor(sentiment));

  useEffect(() => {
    const observer = new MutationObserver(() =>
      setColor(resolveColor(sentiment))
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, [sentiment]);

  return color;
}

export function Sparkline({
  data,
  width = 80,
  height = 32,
  sentiment = "neutral",
}: SparklineProps) {
  const color = useSparklineColor(sentiment);

  if (!data || data.length < 2) return null;

  const points = data.map((v) => ({ v }));
  const label =
    sentiment === "bullish"
      ? "Bullish trend sparkline"
      : sentiment === "bearish"
        ? "Bearish trend sparkline"
        : "Neutral trend sparkline";

  return (
    <LineChart
      width={width}
      height={height}
      data={points}
      margin={{ top: 2, right: 2, bottom: 2, left: 2 }}
      role="img"
      aria-label={label}
    >
      <Line
        type="monotone"
        dataKey="v"
        stroke={color}
        strokeWidth={1.5}
        dot={false}
        activeDot={false}
        isAnimationActive={false}
      />
    </LineChart>
  );
}
