import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Link } from "react-router-dom";
import { ScoreBadge } from "@/components/shared/ScoreBadge";
import { SignalBadge } from "@/components/shared/SignalBadge";
import { ChangeIndicator } from "@/components/shared/ChangeIndicator";
import { RefreshIndicator } from "@/components/shared/RefreshIndicator";
import { Sparkline } from "@/components/shared/Sparkline";
import { AllocationDonut } from "@/components/shared/AllocationDonut";
import { MOCK_SECTORS_FULL, MOCK_POSITIONS, type WatchlistStock } from "@/lib/mock-data";
import { useStockRefresh } from "@/contexts/StockRefreshContext";
import { ChevronDown, ChevronRight, ToggleLeft, ToggleRight, Grid3X3 } from "lucide-react";

// Group stocks by sector
function getStocksBySector(stocks: WatchlistStock[]) {
  const map = new Map<string, WatchlistStock[]>();
  stocks.forEach((s) => {
    if (!map.has(s.sector)) map.set(s.sector, []);
    map.get(s.sector)!.push(s);
  });
  return map;
}

// Generate fake correlation data for a sector
function generateCorrelationMatrix(stocks: WatchlistStock[]) {
  const tickers = stocks.map((s) => s.ticker);
  const matrix: number[][] = [];
  for (let i = 0; i < tickers.length; i++) {
    const row: number[] = [];
    for (let j = 0; j < tickers.length; j++) {
      if (i === j) row.push(1);
      else if (j < i) row.push(matrix[j][i]); // symmetric
      else row.push(Math.round((0.2 + Math.random() * 0.7) * 100) / 100);
    }
    matrix.push(row);
  }
  return { tickers, matrix };
}

function correlationColor(val: number): string {
  if (val >= 0.8) return "bg-loss/60";
  if (val >= 0.6) return "bg-warning/40";
  if (val >= 0.4) return "bg-warning/20";
  if (val >= 0.2) return "bg-gain/20";
  return "bg-gain/40";
}

export default function Sectors() {
  const { allStocks } = useStockRefresh();
  const [expandedSector, setExpandedSector] = useState<string | null>(null);
  const [portfolioOnly, setPortfolioOnly] = useState(false);
  const [showCorrelation, setShowCorrelation] = useState(false);
  const [correlationSector, setCorrelationSector] = useState<string | null>(null);

  const portfolioTickers = useMemo(() => new Set(MOCK_POSITIONS.map((p) => p.ticker)), []);
  const sectorMap = useMemo(() => getStocksBySector(allStocks), [allStocks]);
  const sectorNames = useMemo(() => [...sectorMap.keys()].sort(), [sectorMap]);

  const getFilteredStocks = (sector: string) => {
    const stocks = sectorMap.get(sector) || [];
    if (portfolioOnly) return stocks.filter((s) => portfolioTickers.has(s.ticker));
    return stocks.sort((a, b) => b.compositeScore - a.compositeScore);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-3">
          <Link to="/" className="hover:text-foreground transition-colors">Dashboard</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="text-foreground font-medium">Sectors</span>
        </div>
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">Sector Performance</h1>
          <div className="flex items-center gap-3">
            {/* Portfolio filter toggle */}
            <button
              onClick={() => setPortfolioOnly(!portfolioOnly)}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all border",
                portfolioOnly
                  ? "bg-primary/10 text-primary border-primary/25"
                  : "bg-card2 text-muted-foreground border-border hover:text-foreground"
              )}
            >
              {portfolioOnly ? <ToggleRight className="h-3.5 w-3.5" /> : <ToggleLeft className="h-3.5 w-3.5" />}
              {portfolioOnly ? "Portfolio Only" : "All Stocks"}
            </button>
            {/* Correlation toggle */}
            <button
              onClick={() => setShowCorrelation(!showCorrelation)}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all border",
                showCorrelation
                  ? "bg-primary/10 text-primary border-primary/25"
                  : "bg-card2 text-muted-foreground border-border hover:text-foreground"
              )}
            >
              <Grid3X3 className="h-3.5 w-3.5" />
              Correlation
            </button>
          </div>
        </div>
      </motion.div>

      {/* Sector allocation overview */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-lg border border-border bg-card p-5"
      >
        <AllocationDonut sectors={MOCK_SECTORS_FULL} size={120} />
      </motion.div>

      {/* Sector Accordions */}
      <div className="space-y-3">
        {sectorNames.map((sector, si) => {
          const stocks = getFilteredStocks(sector);
          const isExpanded = expandedSector === sector;
          const sectorColor = MOCK_SECTORS_FULL.find((s) => s.sector === sector)?.color || "hsl(187, 82%, 54%)";
          const avgScore = stocks.length ? stocks.reduce((s, st) => s + st.compositeScore, 0) / stocks.length : 0;
          const avgReturn = stocks.length ? stocks.reduce((s, st) => s + st.annualReturn, 0) / stocks.length : 0;

          return (
            <motion.div
              key={sector}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + si * 0.05 }}
              className="rounded-lg border border-border bg-card overflow-hidden"
            >
              {/* Sector header */}
              <button
                onClick={() => setExpandedSector(isExpanded ? null : sector)}
                className="flex w-full items-center gap-3 px-4 py-3 hover:bg-hov transition-colors"
              >
                <span className="h-3 w-3 rounded-sm shrink-0" style={{ backgroundColor: sectorColor }} />
                <span className="text-sm font-medium flex-1 text-left">{sector}</span>
                <span className="text-[10px] text-muted-foreground">{stocks.length} stock{stocks.length !== 1 ? "s" : ""}</span>
                <span className="font-mono text-xs">Avg Score: <span className={avgScore >= 5 ? "text-gain" : avgScore >= 3 ? "text-warning" : "text-loss"}>{avgScore.toFixed(1)}</span></span>
                <ChangeIndicator value={avgReturn} className="text-[10px]" />
                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", isExpanded && "rotate-180")} />
              </button>

              {/* Expanded content */}
              {isExpanded && stocks.length > 0 && (
                <div className="border-t border-border">
                  {/* Comparison Table */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-card2">
                        <tr className="border-b border-border">
                          {["Ticker", "Name", "Price", "Change", "Score", "RSI", "MACD", "SMA", "Return", "Volatility", "Sharpe", "Fresh"].map((h) => (
                            <th key={h} className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {stocks.map((s) => {
                          const inPortfolio = portfolioTickers.has(s.ticker);
                          return (
                            <tr key={s.ticker} className={cn("border-b border-border/50 hover:bg-hov transition-colors", inPortfolio && "bg-primary/5")}>
                              <td className="px-3 py-2.5">
                                <Link to={`/stocks/${s.ticker}`} className="font-mono font-bold hover:text-primary transition-colors">
                                  {s.ticker}
                                  {inPortfolio && <span className="ml-1 text-[8px] text-primary">●</span>}
                                </Link>
                              </td>
                              <td className="px-3 py-2.5 text-muted-foreground truncate max-w-[120px]">{s.name}</td>
                              <td className="px-3 py-2.5 font-mono">${s.price.toFixed(2)}</td>
                              <td className="px-3 py-2.5"><ChangeIndicator value={s.changePct} className="text-[10px]" /></td>
                              <td className="px-3 py-2.5"><ScoreBadge score={s.compositeScore} size="xs" /></td>
                              <td className="px-3 py-2.5">
                                <div className="flex items-center gap-1">
                                  <span className="font-mono">{s.rsiValue.toFixed(0)}</span>
                                  <SignalBadge value={s.rsiSignal} size="sm" />
                                </div>
                              </td>
                              <td className="px-3 py-2.5">
                                <div className="flex items-center gap-1">
                                  <span className="font-mono">{s.macdValue.toFixed(2)}</span>
                                  <SignalBadge value={s.macdSignal} size="sm" />
                                </div>
                              </td>
                              <td className="px-3 py-2.5"><SignalBadge value={s.smaSignal} size="sm" /></td>
                              <td className="px-3 py-2.5"><ChangeIndicator value={s.annualReturn} className="text-[10px]" /></td>
                              <td className="px-3 py-2.5 font-mono">{s.volatility.toFixed(1)}%</td>
                              <td className="px-3 py-2.5 font-mono">
                                <span className={s.sharpe >= 1 ? "text-gain" : s.sharpe >= 0 ? "text-foreground" : "text-loss"}>
                                  {s.sharpe.toFixed(2)}
                                </span>
                              </td>
                              <td className="px-3 py-2.5">
                                <RefreshIndicator ticker={s.ticker} />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Correlation Matrix for this sector */}
                  {showCorrelation && stocks.length >= 2 && (
                    <CorrelationHeatmap stocks={stocks} portfolioTickers={portfolioTickers} />
                  )}
                </div>
              )}

              {isExpanded && stocks.length === 0 && (
                <div className="border-t border-border px-4 py-6 text-center text-xs text-muted-foreground">
                  No {portfolioOnly ? "portfolio " : ""}stocks in this sector
                </div>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Legend */}
      {showCorrelation && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-lg border border-border bg-card p-4"
        >
          <h3 className="text-xs font-medium mb-3">Correlation Legend</h3>
          <div className="flex items-center gap-4 text-[10px]">
            <span className="flex items-center gap-1.5"><span className="h-3 w-6 rounded-sm bg-gain/40" /> Low (0-0.2) — Good diversification</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-6 rounded-sm bg-gain/20" /> Moderate (0.2-0.4)</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-6 rounded-sm bg-warning/20" /> Medium (0.4-0.6)</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-6 rounded-sm bg-warning/40" /> High (0.6-0.8)</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-6 rounded-sm bg-loss/60" /> Very High (0.8+) — Redundant</span>
          </div>
          <p className="text-[9px] text-muted-foreground mt-2">Stocks with high correlation move together — holding multiple high-correlation stocks reduces diversification benefit.</p>
        </motion.div>
      )}
    </div>
  );
}

// ======================== Correlation Heatmap ========================

function CorrelationHeatmap({ stocks, portfolioTickers }: { stocks: WatchlistStock[]; portfolioTickers: Set<string> }) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const { tickers, matrix } = useMemo(() => generateCorrelationMatrix(stocks), [stocks]);
  const [viewMode, setViewMode] = useState<"heatmap" | "table">("heatmap");

  // Sorted correlation table for selected ticker
  const sortedCorrelations = useMemo(() => {
    if (!selectedTicker) return [];
    const idx = tickers.indexOf(selectedTicker);
    if (idx === -1) return [];
    return tickers
      .map((t, i) => ({ ticker: t, correlation: matrix[idx][i], inPortfolio: portfolioTickers.has(t) }))
      .filter((c) => c.ticker !== selectedTicker)
      .sort((a, b) => a.correlation - b.correlation);
  }, [selectedTicker, tickers, matrix, portfolioTickers]);

  return (
    <div className="border-t border-border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium">Correlation Matrix</h3>
        <div className="flex gap-0.5 rounded-lg bg-card2 p-0.5">
          <button
            onClick={() => setViewMode("heatmap")}
            className={cn("rounded-md px-2 py-1 text-[10px] font-medium transition-colors", viewMode === "heatmap" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}
          >
            Heatmap
          </button>
          <button
            onClick={() => setViewMode("table")}
            className={cn("rounded-md px-2 py-1 text-[10px] font-medium transition-colors", viewMode === "table" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground")}
          >
            Table
          </button>
        </div>
      </div>

      {viewMode === "heatmap" ? (
        <div className="overflow-x-auto">
          <div className="inline-grid" style={{ gridTemplateColumns: `60px repeat(${tickers.length}, 48px)` }}>
            {/* Header row */}
            <div />
            {tickers.map((t) => (
              <div key={`h-${t}`} className="text-center text-[9px] font-mono font-bold py-1 truncate">{t}</div>
            ))}
            {/* Data rows */}
            {tickers.map((rowTicker, ri) => (
              <>
                <div key={`l-${rowTicker}`} className="flex items-center text-[9px] font-mono font-bold pr-2">
                  {rowTicker}
                  {portfolioTickers.has(rowTicker) && <span className="ml-0.5 text-primary">●</span>}
                </div>
                {matrix[ri].map((val, ci) => (
                  <button
                    key={`c-${ri}-${ci}`}
                    onClick={() => setSelectedTicker(ri === ci ? null : rowTicker)}
                    className={cn(
                      "h-10 flex items-center justify-center text-[9px] font-mono border border-border/30 rounded-sm transition-all hover:ring-1 hover:ring-primary/30",
                      ri === ci ? "bg-card2" : correlationColor(val),
                      selectedTicker === rowTicker && "ring-1 ring-primary"
                    )}
                  >
                    {ri === ci ? "—" : val.toFixed(2)}
                  </button>
                ))}
              </>
            ))}
          </div>
        </div>
      ) : (
        <div>
          {!selectedTicker ? (
            <p className="text-xs text-muted-foreground py-4 text-center">Click a ticker below to see its correlations ranked</p>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <div className="bg-card2 px-3 py-2 border-b border-border flex items-center justify-between">
                <span className="text-xs font-medium">Correlations with <span className="font-mono text-primary">{selectedTicker}</span></span>
                <button onClick={() => setSelectedTicker(null)} className="text-[10px] text-muted-foreground hover:text-foreground">Clear</button>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-3 py-1.5 text-left text-[10px] text-muted-foreground">Ticker</th>
                    <th className="px-3 py-1.5 text-left text-[10px] text-muted-foreground">Correlation</th>
                    <th className="px-3 py-1.5 text-left text-[10px] text-muted-foreground">Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCorrelations.map((c) => (
                    <tr key={c.ticker} className={cn("border-b border-border/50", c.inPortfolio && "bg-primary/5")}>
                      <td className="px-3 py-2 font-mono font-bold">
                        {c.ticker}
                        {c.inPortfolio && <span className="ml-1 text-[8px] text-primary">● portfolio</span>}
                      </td>
                      <td className="px-3 py-2">
                        <span className={cn(
                          "font-mono px-1.5 py-0.5 rounded text-[10px]",
                          c.correlation >= 0.8 ? "bg-loss/15 text-loss" :
                          c.correlation >= 0.6 ? "bg-warning/15 text-warning" :
                          c.correlation >= 0.4 ? "bg-foreground/10 text-foreground" :
                          "bg-gain/15 text-gain"
                        )}>
                          {c.correlation.toFixed(2)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-[10px] text-muted-foreground">
                        {c.correlation >= 0.8 ? "Very high — redundant diversification" :
                         c.correlation >= 0.6 ? "High — limited diversification benefit" :
                         c.correlation >= 0.4 ? "Moderate — some diversification" :
                         c.correlation >= 0.2 ? "Low — good diversification" :
                         "Very low — excellent diversification"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {/* Ticker buttons */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {tickers.map((t) => (
              <button
                key={t}
                onClick={() => setSelectedTicker(t === selectedTicker ? null : t)}
                className={cn(
                  "rounded-md px-2 py-1 text-[10px] font-mono font-bold border transition-colors",
                  t === selectedTicker
                    ? "bg-primary/15 text-primary border-primary/25"
                    : "bg-card2 text-muted-foreground border-border hover:text-foreground"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
