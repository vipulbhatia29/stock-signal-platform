"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Activity, Bot } from "lucide-react";
import { TickerSearch } from "@/components/ticker-search";
import { isNYSEOpen } from "@/lib/market-hours";
import { useWatchlist } from "@/hooks/use-stocks";
import { useChat } from "@/contexts/chat-context";
import { AlertBell } from "@/components/alert-bell";
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
  const router = useRouter();
  const { chatOpen, toggleChat } = useChat();

  // Defer market-status to client to avoid SSR hydration mismatch (KAN-98).
  // Use ref + effect to avoid ESLint set-state-in-effect rule. The ref updates
  // the DOM directly after mount — no re-render needed for this static indicator.
  const marketRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = marketRef.current;
    if (!el) return;
    const open = isNYSEOpen();
    const dot = el.querySelector<HTMLSpanElement>("[data-market-dot]");
    const label = el.querySelector<HTMLSpanElement>("[data-market-label]");
    if (dot) {
      dot.className = cn(
        "h-1.5 w-1.5 rounded-full",
        open ? "bg-gain animate-pulse-subtle" : "bg-muted-foreground"
      );
    }
    if (label) label.textContent = open ? "Market Open" : "Market Closed";
    el.style.visibility = "visible";
  }, []);

  const { data: watchlist } = useWatchlist();
  // Matches backend: BUY >= 8, AVOID < 5
  const buyCount = watchlist?.filter((w) => (w.composite_score ?? 0) >= 8).length ?? 0;
  const sellCount = watchlist?.filter((w) => (w.composite_score ?? 0) < 5).length ?? 0;
  const totalSignals = buyCount + sellCount;

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
        {/* Market status — hidden until client hydrates via ref */}
        <div ref={marketRef} className="flex items-center gap-1.5" style={{ visibility: "hidden" }}>
          <span data-market-dot className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          <span data-market-label className="text-[10px] text-muted-foreground">
            Market Closed
          </span>
        </div>

        {/* Signal count — shows BUY and SELL counts */}
        {totalSignals > 0 && (
          <button
            onClick={() => router.push("/screener")}
            className="flex items-center gap-1.5 rounded-md bg-card2 border border-border px-2 py-1 hover:bg-hov transition-colors"
            title="View signals in screener"
          >
            <Activity size={12} className="text-cyan" />
            {buyCount > 0 && (
              <span className="font-mono text-[10px] text-gain font-semibold">{buyCount} BUY</span>
            )}
            {sellCount > 0 && (
              <span className="font-mono text-[10px] text-loss font-semibold">{sellCount} AVOID</span>
            )}
          </button>
        )}

        {/* Alert bell */}
        <AlertBell />

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
