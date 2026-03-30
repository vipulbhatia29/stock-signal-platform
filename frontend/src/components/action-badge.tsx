import { cn } from "@/lib/utils";

type BadgeVariant = "strong-buy" | "buy" | "watch" | "sell" | "hold";

interface ActionBadgeProps {
  action: string;
  className?: string;
}

function getVariant(action: string): BadgeVariant {
  const upper = action.toUpperCase();
  if (upper === "STRONG_BUY" || upper === "STRONG BUY") return "strong-buy";
  if (upper === "BUY") return "buy";
  if (upper === "WATCH" || upper === "AVOID") return "watch";
  if (upper === "SELL") return "sell";
  return "hold";
}

const VARIANT_STYLES: Record<BadgeVariant, string> = {
  "strong-buy": "bg-gain/15 text-[var(--gain)]",
  buy: "bg-gain/15 text-[var(--gain)]",
  watch: "bg-warning/15 text-[var(--warning)]",
  sell: "bg-loss/15 text-[var(--loss)]",
  hold: "bg-muted/15 text-muted-foreground",
};

const VARIANT_LABELS: Record<BadgeVariant, string> = {
  "strong-buy": "Strong Buy",
  buy: "Buy",
  watch: "Watch",
  sell: "Sell",
  hold: "Hold",
};

export function ActionBadge({ action, className }: ActionBadgeProps) {
  const variant = getVariant(action);
  return (
    <span
      className={cn(
        "rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        VARIANT_STYLES[variant],
        className,
      )}
    >
      {VARIANT_LABELS[variant]}
    </span>
  );
}
