import { Activity, Bell, Bot, RefreshCw, Search } from "lucide-react";
import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useChat } from "@/contexts/ChatContext";
import { useStockRefresh } from "@/contexts/StockRefreshContext";

const ROUTE_NAMES: Record<string, string> = {
  "/": "Dashboard",
  "/screener": "Screener",
  "/portfolio": "Portfolio",
  "/sectors": "Sectors",
};

export function Topbar() {
  const { chatOpen, toggleChat } = useChat();
  const { refreshAll, refreshingAll } = useStockRefresh();
  const { pathname } = useLocation();
  const pageName = pathname.startsWith("/stocks/")
    ? pathname.split("/").pop()?.toUpperCase()
    : ROUTE_NAMES[pathname] || "Page";

  const isMarketOpen = (() => {
    const et = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
    const d = et.getDay(), m = et.getHours() * 60 + et.getMinutes();
    return d >= 1 && d <= 5 && m >= 570 && m < 960;
  })();

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">StockSignal</span>
          <span className="text-muted-foreground">/</span>
          <span className="font-medium text-foreground">{pageName}</span>
        </div>
      </div>

      {/* Search */}
      <div className="hidden md:flex items-center gap-2 rounded-lg bg-card2 border border-border px-3 py-1.5 w-72">
        <Search className="h-3.5 w-3.5 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search stocks to add..."
          className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        <kbd className="rounded bg-muted px-1 py-0.5 text-[9px] text-muted-foreground font-mono">/</kbd>
        <button
          onClick={refreshAll}
          disabled={refreshingAll}
          title="Refresh all stock data"
          className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-muted-foreground hover:text-foreground hover:bg-hov transition-colors disabled:pointer-events-none"
        >
          <RefreshCw className={cn("h-3 w-3", refreshingAll && "animate-spin")} />
        </button>
      </div>

      <div className="flex items-center gap-2">
        {/* Market status */}
        <div className="flex items-center gap-1.5">
          <span className={cn(
            "h-1.5 w-1.5 rounded-full",
            isMarketOpen ? "bg-gain animate-pulse-subtle" : "bg-muted-foreground"
          )} />
          <span className="text-[10px] text-muted-foreground">{isMarketOpen ? "Market Open" : "Market Closed"}</span>
        </div>

        {/* Signal count */}
        <button className="flex items-center gap-1.5 rounded-md bg-card2 border border-border px-2 py-1 hover:bg-hov transition-colors">
          <Activity className="h-3 w-3 text-primary" />
          <span className="font-mono text-[10px] text-foreground">5 signals</span>
        </button>

        <button className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-hov hover:text-foreground transition-colors">
          <Bell className="h-4 w-4" />
        </button>




        <button
          onClick={toggleChat}
          className={cn(
            "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
            chatOpen
              ? "bg-primary/15 text-primary border border-primary/25"
              : "bg-card2 border border-border text-muted-foreground hover:bg-hov hover:text-foreground"
          )}
        >
          <Bot className="h-3.5 w-3.5" />
          <span>AI Analyst</span>
        </button>
      </div>
    </header>
  );
}
