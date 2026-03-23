import { cn } from "@/lib/utils";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
  strokeWidth?: number;
}

export function Sparkline({ data, width = 100, height = 32, className, strokeWidth = 1.5 }: SparklineProps) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((val, i) => `${(i / (data.length - 1)) * width},${height - ((val - min) / range) * (height - 4) - 2}`)
    .join(" ");
  const isPositive = data[data.length - 1] >= data[0];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={cn("overflow-visible", className)}>
      <polyline
        points={points}
        fill="none"
        stroke={isPositive ? "hsl(var(--gain))" : "hsl(var(--loss))"}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
