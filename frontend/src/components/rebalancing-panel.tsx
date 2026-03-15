"use client";

import { RebalancingSuggestion } from "@/types/api";
import { SectionHeading } from "@/components/section-heading";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  suggestions: RebalancingSuggestion[];
}

const ACTION_LABEL: Record<RebalancingSuggestion["action"], string> = {
  BUY_MORE: "Buy more",
  HOLD: "Hold",
  AT_CAP: "At cap",
};

export function RebalancingPanel({ suggestions }: Props) {
  const actionable = suggestions.filter((s) => s.action === "BUY_MORE");

  if (suggestions.length === 0) return null;

  const subtitle =
    actionable.length > 0
      ? `${actionable.length} position${actionable.length > 1 ? "s" : ""} under target allocation`
      : "All positions at target allocation";

  return (
    <div className="mt-6">
      <SectionHeading>
        <span>Rebalancing</span>
        <span className="ml-2 text-xs font-normal text-muted-foreground normal-case tracking-normal">
          {subtitle}
        </span>
      </SectionHeading>
      <div className="rounded-lg border border-border overflow-hidden mt-3">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                Ticker
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground">
                Current
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground">
                Target
              </th>
              <th className="text-center px-4 py-2 font-medium text-muted-foreground">
                Action
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground">
                Suggested
              </th>
            </tr>
          </thead>
          <tbody>
            {suggestions.map((s) => (
              <tr
                key={s.ticker}
                className={cn(
                  "border-b border-border last:border-0 transition-colors hover:bg-muted/20",
                  s.action === "BUY_MORE" &&
                    "border-l-2 border-l-[var(--color-gain)]"
                )}
              >
                <td className="px-4 py-2.5 font-mono font-medium">
                  {s.ticker}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">
                  {s.current_allocation_pct != null
                    ? `${s.current_allocation_pct.toFixed(1)}%`
                    : "—"}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                  {s.target_allocation_pct.toFixed(1)}%
                </td>
                <td className="px-4 py-2.5 text-center">
                  <Badge
                    variant={
                      s.action === "BUY_MORE"
                        ? "default"
                        : s.action === "AT_CAP"
                          ? "outline"
                          : "secondary"
                    }
                    className={cn(
                      s.action === "AT_CAP" &&
                        "text-amber-500 border-amber-500"
                    )}
                  >
                    {ACTION_LABEL[s.action]}
                  </Badge>
                </td>
                <td
                  className={cn(
                    "px-4 py-2.5 text-right tabular-nums font-medium",
                    s.action === "BUY_MORE" && "text-[var(--color-gain)]"
                  )}
                >
                  {s.suggested_amount > 0
                    ? `$${s.suggested_amount.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        Targets based on equal-weight across {suggestions.length} positions,
        capped by your concentration limits.
      </p>
    </div>
  );
}
