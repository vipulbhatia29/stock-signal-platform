import { cn } from "@/lib/utils";

type SignalValue = string;

interface SignalBadgeProps {
  type?: string;
  value: SignalValue;
  size?: "sm" | "md";
}

const SIGNAL_STYLES: Record<string, string> = {
  BULLISH: "bg-gain/10 text-gain",
  BEARISH: "bg-loss/10 text-loss",
  OVERSOLD: "bg-warning/10 text-warning",
  OVERBOUGHT: "bg-loss/10 text-loss",
  NEUTRAL: "bg-muted text-muted-foreground",
  GOLDEN_CROSS: "bg-gain/10 text-gain",
  DEATH_CROSS: "bg-loss/10 text-loss",
  ABOVE_200: "bg-gain/10 text-gain",
  BELOW_200: "bg-loss/10 text-loss",
  UPPER: "bg-loss/10 text-loss",
  MIDDLE: "bg-muted text-muted-foreground",
  LOWER: "bg-gain/10 text-gain",
  BUY: "bg-gain/15 text-gain border border-gain/20",
  HOLD: "bg-warning/15 text-warning border border-warning/20",
  SELL: "bg-loss/15 text-loss border border-loss/20",
  WATCH: "bg-cyan/15 text-cyan border border-cyan/20",
  AVOID: "bg-loss/15 text-loss border border-loss/20",
};

const LABELS: Record<string, string> = {
  GOLDEN_CROSS: "Golden ×",
  DEATH_CROSS: "Death ×",
  ABOVE_200: "Above 200",
  BELOW_200: "Below 200",
};

export function SignalBadge({ type, value, size = "sm" }: SignalBadgeProps) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded font-medium",
      SIGNAL_STYLES[value] || "bg-muted text-muted-foreground",
      size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"
    )}>
      {type && <span className="opacity-50">{type}</span>}
      <span>{LABELS[value] || value}</span>
    </span>
  );
}
