"use client";

// Sparkline — raw SVG polyline for realistic jagged financial chart appearance.
// Replaces Recharts LineChart (smooth bezier) which looked too smooth for price data.
// Backward compatible: existing `sentiment` prop still works.

import { CSS_VARS } from "@/lib/design-tokens";

function readCssVar(name: string): string {
  if (typeof window === "undefined") return "#22d3a0";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function resolveColor(
  sentiment: "bullish" | "bearish" | "neutral",
  color?: string
): string {
  if (color) return color;
  if (sentiment === "bullish") return readCssVar(CSS_VARS.gain);
  if (sentiment === "bearish") return readCssVar(CSS_VARS.loss);
  return readCssVar(CSS_VARS.neutralSignal);
}

interface SparklineProps {
  data: number[];
  volumes?: number[];
  color?: string;
  sentiment?: "bullish" | "bearish" | "neutral";
  width?: number;
  height?: number;
}

export function Sparkline({
  data,
  volumes,
  color,
  sentiment = "neutral",
  width = 120,
  height = 40,
}: SparklineProps) {
  if (!data || data.length < 2) return null;

  const strokeColor = resolveColor(sentiment, color);
  const VOLUME_ZONE = height * 0.22; // bottom 22% for volume bars
  const PRICE_HEIGHT = height - VOLUME_ZONE - 2;

  const minV = Math.min(...data);
  const maxV = Math.max(...data);
  const range = maxV - minV || 1;

  // Map data to SVG coordinates
  const step = width / (data.length - 1);
  const points = data
    .map((v, i) => {
      const x = i * step;
      const y = PRICE_HEIGHT - ((v - minV) / range) * (PRICE_HEIGHT - 4) + 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Volume bars
  let volumeBars: React.ReactNode = null;
  if (volumes && volumes.length > 0) {
    const maxVol = Math.max(...volumes) || 1;
    const barWidth = (width / volumes.length) * 0.7;
    volumeBars = volumes.map((vol, i) => {
      const barH = (vol / maxVol) * (VOLUME_ZONE - 1);
      const x = i * (width / volumes.length) + (width / volumes.length - barWidth) / 2;
      const y = height - barH;
      return (
        <rect
          key={i}
          x={x.toFixed(1)}
          y={y.toFixed(1)}
          width={barWidth.toFixed(1)}
          height={barH.toFixed(1)}
          fill={strokeColor}
          opacity={0.35}
        />
      );
    });
  }

  const label =
    sentiment === "bullish"
      ? "Bullish trend"
      : sentiment === "bearish"
        ? "Bearish trend"
        : "Price trend";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
      style={{ overflow: "visible" }}
    >
      {volumeBars}
      <polyline
        points={points}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
