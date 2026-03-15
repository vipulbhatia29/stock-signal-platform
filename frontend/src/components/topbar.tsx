"use client";

import { usePathname } from "next/navigation";
import { BotIcon } from "lucide-react";
import { TickerSearch } from "@/components/ticker-search";
import { isNYSEOpen } from "@/lib/market-hours";
import { useWatchlist } from "@/hooks/use-stocks";
import { cn } from "@/lib/utils";

interface TopbarProps {
  chatIsOpen: boolean;
  onToggleChat: () => void;
  onAddTicker: (ticker: string) => void;
}

const PAGE_LABELS: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/screener": "Screener",
  "/portfolio": "Portfolio",
};

export function Topbar({ chatIsOpen, onToggleChat, onAddTicker }: TopbarProps) {
  const pathname = usePathname();
  const marketOpen = isNYSEOpen();

  const { data: watchlist } = useWatchlist();
  const signalCount =
    watchlist?.filter((w) => (w.composite_score ?? 0) >= 0.6).length ?? 0;

  // Derive page label — check exact match first, then startsWith for sub-routes
  const pageLabel =
    PAGE_LABELS[pathname] ??
    Object.entries(PAGE_LABELS).find(([k]) => pathname.startsWith(k))?.[1] ??
    "StockSignal";

  return (
    <header
      className="flex items-center justify-between flex-shrink-0 border-b border-border bg-background px-[18px]"
      style={{ height: "46px" }}
    >
      {/* Left: breadcrumb */}
      <div className="flex items-center gap-1.5 text-[11.5px]">
        <span className="text-subtle font-medium">StockSignal</span>
        <span className="text-subtle">/</span>
        <span className="text-foreground font-semibold text-[13px]">{pageLabel}</span>
      </div>

      {/* Center: search */}
      <TickerSearch onSelect={onAddTicker} />

      {/* Right: chips + AI toggle */}
      <div className="flex items-center gap-2">
        {/* Market status chip */}
        <div className="flex items-center gap-1.5 bg-card border border-border rounded-full px-2.5 py-1 text-[11px] text-muted-foreground">
          <span
            className={cn(
              "w-[5px] h-[5px] rounded-full",
              marketOpen
                ? "bg-gain shadow-[0_0_5px_var(--gain)]"
                : "bg-subtle"
            )}
          />
          {marketOpen ? "Market Open" : "Market Closed"}
        </div>

        {/* Signal count chip */}
        {signalCount > 0 && (
          <div className="flex items-center gap-1.5 bg-card border border-border rounded-full px-2.5 py-1 text-[11px] text-muted-foreground">
            <BotIcon size={11} />
            {signalCount} signal{signalCount !== 1 ? "s" : ""}
          </div>
        )}

        {/* AI Analyst toggle */}
        <button
          onClick={onToggleChat}
          className={cn(
            "flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
            chatIsOpen
              ? "bg-cyan text-[var(--background)]"
              : "bg-[var(--cdim)] border border-[var(--bhi)] text-cyan hover:bg-[rgba(56,189,248,0.2)]"
          )}
        >
          <BotIcon size={12} />
          AI Analyst
        </button>
      </div>
    </header>
  );
}
