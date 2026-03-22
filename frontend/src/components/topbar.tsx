"use client";

import { usePathname } from "next/navigation";
import { Activity, Bell, Bot } from "lucide-react";
import { TickerSearch } from "@/components/ticker-search";
import { isNYSEOpen } from "@/lib/market-hours";
import { useWatchlist } from "@/hooks/use-stocks";
import { useChat } from "@/contexts/chat-context";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface TopbarProps {
  onAddTicker: (ticker: string) => void;
}

const PAGE_LABELS: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/screener": "Screener",
  "/portfolio": "Portfolio",
  "/sectors": "Sectors",
};

export function Topbar({ onAddTicker }: TopbarProps) {
  const pathname = usePathname();
  const marketOpen = isNYSEOpen();
  const { chatOpen, toggleChat } = useChat();

  const { data: watchlist } = useWatchlist();
  const signalCount =
    watchlist?.filter((w) => (w.composite_score ?? 0) >= 0.6).length ?? 0;

  // Derive page label — stock detail shows ticker, otherwise route label
  const pageLabel = pathname.startsWith("/stocks/")
    ? pathname.split("/").pop()?.toUpperCase()
    : PAGE_LABELS[pathname] ??
      Object.entries(PAGE_LABELS).find(([k]) => pathname.startsWith(k))?.[1] ??
      "Dashboard";

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-card px-4">
      {/* Left: breadcrumb */}
      <div className="flex items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">StockSignal</span>
        <span className="text-muted-foreground">/</span>
        <span className="font-medium text-foreground">{pageLabel}</span>
      </div>

      {/* Center: search */}
      <TickerSearch onSelect={onAddTicker} />

      {/* Right: status + controls */}
      <div className="flex items-center gap-2">
        {/* Market status */}
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              marketOpen
                ? "bg-gain animate-pulse-subtle"
                : "bg-muted-foreground"
            )}
          />
          <span className="text-[10px] text-muted-foreground">
            {marketOpen ? "Market Open" : "Market Closed"}
          </span>
        </div>

        {/* Signal count */}
        {signalCount > 0 && (
          <button className="flex items-center gap-1.5 rounded-md bg-card2 border border-border px-2 py-1 hover:bg-hov transition-colors">
            <Activity size={12} className="text-cyan" />
            <span className="font-mono text-[10px] text-foreground">
              {signalCount} signal{signalCount !== 1 ? "s" : ""}
            </span>
          </button>
        )}

        {/* Notification bell — stub */}
        <Tooltip>
          <TooltipTrigger
            render={
              <button className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-hov hover:text-foreground transition-colors">
                <Bell size={16} />
              </button>
            }
          />
          <TooltipContent side="bottom" className="text-xs">
            Notifications (Coming Soon)
          </TooltipContent>
        </Tooltip>

        {/* AI Analyst toggle */}
        <button
          onClick={toggleChat}
          className={cn(
            "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
            chatOpen
              ? "bg-[var(--cdim)] text-cyan border border-[var(--bhi)] shadow-[0_0_20px_var(--cyan-muted)]"
              : "bg-card2 border border-border text-muted-foreground hover:bg-hov hover:text-foreground"
          )}
        >
          <Bot size={14} />
          <span>AI Analyst</span>
        </button>
      </div>
    </header>
  );
}
