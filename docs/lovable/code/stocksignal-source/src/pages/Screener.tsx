import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";
import { ScoreBadge } from "@/components/shared/ScoreBadge";
import { SignalBadge } from "@/components/shared/SignalBadge";
import { Sparkline } from "@/components/shared/Sparkline";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { ChangeIndicator } from "@/components/shared/ChangeIndicator";
import { RefreshIndicator } from "@/components/shared/RefreshIndicator";
import { MOCK_POSITIONS, type WatchlistStock } from "@/lib/mock-data";
import { useChat } from "@/contexts/ChatContext";
import { useStockRefresh } from "@/contexts/StockRefreshContext";
import { ArrowUpDown, LayoutGrid, List, ChevronLeft, ChevronRight, RotateCcw, Briefcase } from "lucide-react";

type TabId = "overview" | "signals" | "performance";
type ViewMode = "table" | "grid";
type Density = "comfortable" | "compact";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "signals", label: "Signals" },
  { id: "performance", label: "Performance" },
];

export default function Screener() {
  const { chatOpen } = useChat();
  const { allStocks } = useStockRefresh();
  const isNarrow = chatOpen;
  const portfolioTickers = useMemo(() => new Set(MOCK_POSITIONS.map((p) => p.ticker)), []);
  const [tab, setTab] = useState<TabId>("overview");
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [density, setDensity] = useState<Density>("comfortable");
  const [sortBy, setSortBy] = useState<string>("compositeScore");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Filters
  const [rsiFilter, setRsiFilter] = useState<string>("all");
  const [macdFilter, setMacdFilter] = useState<string>("all");
  const [sectorFilter, setSectorFilter] = useState<string>("all");

  const stocks = useMemo(() => {
    let filtered = [...allStocks];
    if (rsiFilter !== "all") filtered = filtered.filter((s) => s.rsiSignal === rsiFilter);
    if (macdFilter !== "all") filtered = filtered.filter((s) => s.macdSignal === macdFilter);
    if (sectorFilter !== "all") filtered = filtered.filter((s) => s.sector === sectorFilter);
    filtered.sort((a, b) => {
      const av = (a as any)[sortBy] ?? 0;
      const bv = (b as any)[sortBy] ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return filtered;
  }, [allStocks, rsiFilter, macdFilter, sectorFilter, sortBy, sortDir]);

  const sectors: string[] = [...new Set(allStocks.map((s) => s.sector))];
  const hasFilters = rsiFilter !== "all" || macdFilter !== "all" || sectorFilter !== "all";

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir(sortDir === "desc" ? "asc" : "desc");
    else { setSortBy(col); setSortDir("desc"); }
  };

  return (
    <div className="p-6 space-y-4">
      {/* Filters */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center gap-2">
        <FilterSelect label="RSI" value={rsiFilter} onChange={setRsiFilter} options={["all", "OVERSOLD", "NEUTRAL", "OVERBOUGHT"]} />
        <FilterSelect label="MACD" value={macdFilter} onChange={setMacdFilter} options={["all", "BULLISH", "BEARISH"]} />
        <FilterSelect label="Sector" value={sectorFilter} onChange={setSectorFilter} options={["all", ...sectors]} />

        {hasFilters && (
          <button
            onClick={() => { setRsiFilter("all"); setMacdFilter("all"); setSectorFilter("all"); }}
            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="h-3 w-3" /> Reset
          </button>
        )}

        <div className="ml-auto flex items-center gap-2">
          {viewMode === "table" && (
            <button
              onClick={() => setDensity(density === "comfortable" ? "compact" : "comfortable")}
              className="text-[10px] text-muted-foreground hover:text-foreground px-2 py-1 rounded border border-border bg-card"
            >
              {density === "comfortable" ? "Compact" : "Comfortable"}
            </button>
          )}
          <div className="flex rounded-lg border border-border bg-card overflow-hidden">
            <button onClick={() => setViewMode("table")} className={cn("flex h-7 w-7 items-center justify-center transition-colors", viewMode === "table" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}>
              <List className="h-3.5 w-3.5" />
            </button>
            <button onClick={() => setViewMode("grid")} className={cn("flex h-7 w-7 items-center justify-center transition-colors", viewMode === "grid" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}>
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </motion.div>

      {/* Tabs */}
      {viewMode === "table" && (
        <div className="flex gap-0 border-b border-border">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px",
                tab === t.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {viewMode === "table" ? (
        <ScreenerTable stocks={stocks} tab={tab} density={density} sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} portfolioTickers={portfolioTickers} />
      ) : (
        <ScreenerGrid stocks={stocks} isNarrow={isNarrow} portfolioTickers={portfolioTickers} />
      )}

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Showing 1-{stocks.length} of {stocks.length}</span>
        <div className="flex items-center gap-1">
          <button className="flex h-7 w-7 items-center justify-center rounded border border-border bg-card text-muted-foreground hover:text-foreground disabled:opacity-40" disabled>
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="px-2 font-mono">1</span>
          <button className="flex h-7 w-7 items-center justify-center rounded border border-border bg-card text-muted-foreground hover:text-foreground disabled:opacity-40" disabled>
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ======================== Sub-components ========================

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer"
      >
        {options.map((o) => (
          <option key={o} value={o}>{o === "all" ? "All" : o}</option>
        ))}
      </select>
    </div>
  );
}

function SortHeader({ label, col, sortBy, sortDir, onSort }: { label: string; col: string; sortBy: string; sortDir: string; onSort: (col: string) => void }) {
  const active = sortBy === col;
  return (
    <th
      onClick={() => onSort(col)}
      className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:text-foreground select-none"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {active && <ArrowUpDown className="h-2.5 w-2.5 text-primary" />}
      </span>
    </th>
  );
}

function ScreenerTable({ stocks, tab, density, sortBy, sortDir, onSort, portfolioTickers }: {
  stocks: WatchlistStock[]; tab: TabId; density: Density; sortBy: string; sortDir: string; onSort: (col: string) => void; portfolioTickers: Set<string>;
}) {
  const py = density === "compact" ? "py-1.5" : "py-2.5";
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full">
        <thead className="bg-card2">
          <tr className="border-b border-border">
            <th className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider w-20">Ticker</th>
            {tab === "overview" && (
              <>
                <th className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Name</th>
                <th className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Sector</th>
                <th className="px-3 py-2 text-right text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Price</th>
                <th className="px-3 py-2 text-right text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Change</th>
                <SortHeader label="Score" col="compositeScore" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              </>
            )}
            {tab === "signals" && (
              <>
                <SortHeader label="RSI" col="rsiValue" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <th className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">MACD</th>
                <th className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">SMA</th>
                <th className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Bollinger</th>
                <SortHeader label="Score" col="compositeScore" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              </>
            )}
            {tab === "performance" && (
              <>
                <SortHeader label="Ann. Return" col="annualReturn" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortHeader label="Volatility" col="volatility" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortHeader label="Sharpe" col="sharpe" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortHeader label="Score" col="compositeScore" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              </>
            )}
            <th className="px-3 py-2 text-right text-[10px] font-medium text-muted-foreground uppercase tracking-wider w-16">Fresh</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((s, i) => (
            <motion.tr
              key={s.ticker}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.02 }}
            >
              <td className={cn("px-3 border-b border-border/50", py)}>
                <Link to={`/stocks/${s.ticker}`} className="font-mono text-xs font-bold text-foreground hover:text-primary transition-colors inline-flex items-center gap-1.5">
                  {s.ticker}
                  {portfolioTickers.has(s.ticker) && (
                    <span className="flex items-center gap-0.5 rounded bg-primary/10 px-1 py-0.5 text-[8px] font-semibold text-primary">
                      <Briefcase className="h-2.5 w-2.5" />
                    </span>
                  )}
                </Link>
              </td>
              {tab === "overview" && (
                <>
                  <td className={cn("px-3 border-b border-border/50 text-xs text-muted-foreground", py)}>{s.name}</td>
                  <td className={cn("px-3 border-b border-border/50", py)}>
                    <span className="rounded bg-card2 px-1.5 py-0.5 text-[10px] text-muted-foreground">{s.sector}</span>
                  </td>
                  <td className={cn("px-3 border-b border-border/50 text-right font-mono text-xs", py)}>${s.price.toFixed(2)}</td>
                  <td className={cn("px-3 border-b border-border/50 text-right", py)}>
                    <ChangeIndicator value={s.changePct} className="text-[10px]" />
                  </td>
                  <td className={cn("px-3 border-b border-border/50", py)}>
                    <div className="flex items-center gap-2">
                      <ScoreBar score={s.compositeScore} className="w-16" />
                      <ScoreBadge score={s.compositeScore} size="xs" />
                    </div>
                  </td>
                </>
              )}
              {tab === "signals" && (
                <>
                  <td className={cn("px-3 border-b border-border/50", py)}>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs">{s.rsiValue.toFixed(1)}</span>
                      <SignalBadge value={s.rsiSignal} />
                    </div>
                  </td>
                  <td className={cn("px-3 border-b border-border/50", py)}>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs">{s.macdValue.toFixed(2)}</span>
                      <SignalBadge value={s.macdSignal} />
                    </div>
                  </td>
                  <td className={cn("px-3 border-b border-border/50", py)}><SignalBadge value={s.smaSignal} /></td>
                  <td className={cn("px-3 border-b border-border/50", py)}><SignalBadge value={s.bbPosition} /></td>
                  <td className={cn("px-3 border-b border-border/50", py)}><ScoreBadge score={s.compositeScore} size="sm" /></td>
                </>
              )}
              {tab === "performance" && (
                <>
                  <td className={cn("px-3 border-b border-border/50", py)}>
                    <ChangeIndicator value={s.annualReturn} className="text-xs" />
                  </td>
                  <td className={cn("px-3 border-b border-border/50 font-mono text-xs", py)}>{s.volatility.toFixed(1)}%</td>
                  <td className={cn("px-3 border-b border-border/50 font-mono text-xs", py)}>
                    <span className={s.sharpe >= 1 ? "text-gain" : s.sharpe >= 0 ? "text-foreground" : "text-loss"}>
                      {s.sharpe.toFixed(2)}
                    </span>
                  </td>
                  <td className={cn("px-3 border-b border-border/50", py)}><ScoreBadge score={s.compositeScore} size="sm" /></td>
                </>
              )}
              <td className={cn("px-3 border-b border-border/50 text-right", py)}>
                <RefreshIndicator ticker={s.ticker} />
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScreenerGrid({ stocks, isNarrow, portfolioTickers }: { stocks: WatchlistStock[]; isNarrow: boolean; portfolioTickers: Set<string> }) {
  return (
    <div className={cn(
      "grid grid-cols-2 gap-3 transition-all duration-300",
      isNarrow ? "sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" : "sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
    )}>
      {stocks.map((s, i) => (
        <motion.div key={s.ticker} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
          <Link to={`/stocks/${s.ticker}`} className="block rounded-lg border border-border bg-card p-3 transition-colors hover:border-primary/30 hover:bg-hov">
            <Sparkline data={s.priceHistory} width={140} height={40} className="w-full mb-2" />
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1 font-mono text-xs font-bold">
                {s.ticker}
                {portfolioTickers.has(s.ticker) && <Briefcase className="h-2.5 w-2.5 text-primary" />}
              </span>
              <ScoreBadge score={s.compositeScore} size="xs" />
            </div>
            <div className="mt-1 flex items-center justify-between">
              {s.recommendation ? <SignalBadge value={s.recommendation} size="sm" /> : <span />}
              <RefreshIndicator ticker={s.ticker} compact />
            </div>
          </Link>
        </motion.div>
      ))}
    </div>
  );
}
