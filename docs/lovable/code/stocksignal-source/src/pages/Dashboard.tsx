import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/shared/Sparkline";
import { ScoreBadge } from "@/components/shared/ScoreBadge";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { SignalBadge } from "@/components/shared/SignalBadge";
import { AllocationDonut } from "@/components/shared/AllocationDonut";
import { ChangeIndicator } from "@/components/shared/ChangeIndicator";
import { RefreshIndicator } from "@/components/shared/RefreshIndicator";
import { useChat } from "@/contexts/ChatContext";
import { useStockRefresh } from "@/contexts/StockRefreshContext";
import {
  MOCK_STATS, MOCK_INDEXES,
  MOCK_SECTORS, MOCK_RECOMMENDATIONS, MOCK_SECTORS_FULL,
  MOCK_POSITIONS,
  type IndexInfo, type Recommendation,
} from "@/lib/mock-data";
import { useMemo } from "react";
import { ArrowUpRight, ArrowDownRight, Eye, ChevronRight, TrendingDown, Minus, Briefcase } from "lucide-react";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const { chatOpen } = useChat();
  const { allStocks, stocks: stockMap } = useStockRefresh();
  const isNarrow = chatOpen;
  const portfolioTickers = useMemo(() => new Set(MOCK_POSITIONS.map((p) => p.ticker)), []);
  const watchlist = useMemo(() => allStocks.slice(0, 5), [allStocks]);

  return (
    <div className="p-6 space-y-6">
      {/* KPI Stat Tiles */}
      <div className={cn(
        "grid grid-cols-2 gap-3 transition-all duration-300",
        isNarrow ? "lg:grid-cols-3 xl:grid-cols-5" : "lg:grid-cols-5"
      )}>
        {MOCK_STATS.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.05 }}
            className="relative overflow-hidden rounded-lg border border-border bg-card p-4"
          >
            <div className={cn(
              "absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r",
              stat.accent === "cyan" ? "from-primary to-primary/0" :
              stat.accent === "gain" ? "from-gain to-gain/0" :
              stat.accent === "loss" ? "from-loss to-loss/0" :
              "from-warning to-warning/0"
            )} />
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{stat.label}</p>
            {stat.type === "donut" ? (
              <Link to="/sectors" className="mt-2 block cursor-pointer group">
                <AllocationDonut sectors={MOCK_SECTORS} size={50} holeRatio={0.55} />
                <p className="text-[9px] text-muted-foreground group-hover:text-primary transition-colors mt-1">Click to explore sectors →</p>
              </Link>
            ) : stat.type === "signal-summary" ? (
              <>
                <p className="mt-1 font-mono text-xl font-semibold tracking-tight text-gain">{stat.value}</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground">{stat.subValue}</p>
              </>
            ) : (
              <>
                <p className="mt-1 font-mono text-xl font-semibold tracking-tight">{stat.value}</p>
                {stat.subValue && <p className="mt-0.5 text-[10px] text-muted-foreground">{stat.subValue}</p>}
                {stat.change && (
                  <p className={cn(
                    "mt-0.5 font-mono text-[10px]",
                    stat.changeType === "gain" ? "text-gain" : stat.changeType === "loss" ? "text-loss" : "text-muted-foreground"
                  )}>
                    {stat.change}
                  </p>
                )}
              </>
            )}
          </motion.div>
        ))}
      </div>

      {/* Market Indexes */}
      <section>
        <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Market Indexes</h2>
        <div className={cn(
          "grid grid-cols-1 gap-3 transition-all duration-300",
          isNarrow ? "md:grid-cols-2 xl:grid-cols-3" : "md:grid-cols-3"
        )}>
          {MOCK_INDEXES.map((idx, i) => (
            <IndexCard key={idx.slug} data={idx} index={i} />
          ))}
        </div>
      </section>

      {/* Action Required + Allocation */}
      <div className={cn(
        "grid grid-cols-1 gap-6 transition-all duration-300",
        isNarrow ? "lg:grid-cols-1 xl:grid-cols-3" : "lg:grid-cols-3"
      )}>
        <section className={cn(isNarrow ? "xl:col-span-2" : "lg:col-span-2")}>
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Action Required</h2>
          <div className="space-y-2">
            {MOCK_RECOMMENDATIONS.map((rec, i) => {
              const liveStock = stockMap.get(rec.ticker);
              return (
                <RecommendationRow key={rec.ticker} rec={{ ...rec, compositeScore: liveStock?.compositeScore ?? rec.compositeScore }} index={i} />
              );
            })}
          </div>
        </section>
        <div>
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Sector Allocation</h2>
          <Link to="/sectors">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.5 }}
              className="rounded-lg border border-border bg-card p-4 cursor-pointer hover:border-primary/30 transition-colors group"
            >
              <AllocationDonut sectors={MOCK_SECTORS_FULL} size={110} />
              <p className="text-[9px] text-muted-foreground group-hover:text-primary transition-colors mt-3 text-center">Click to explore sector performance →</p>
            </motion.div>
          </Link>
        </div>
      </div>

      {/* Watchlist */}
      <section>
        <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Watchlist</h2>
        <div className={cn(
          "grid grid-cols-1 gap-3 transition-all duration-300",
          isNarrow ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-4"
        )}>
          {watchlist.map((stock, i) => (
            <motion.div
              key={stock.ticker}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.6 + i * 0.05 }}
            >
              <Link
                to={`/stocks/${stock.ticker}`}
                className="group block rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/30 hover:bg-hov"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold">{stock.ticker}</span>
                      {portfolioTickers.has(stock.ticker) && (
                        <span className="flex items-center gap-0.5 rounded bg-primary/10 px-1 py-0.5 text-[8px] font-semibold text-primary">
                          <Briefcase className="h-2.5 w-2.5" /> Held
                        </span>
                      )}
                      <ScoreBadge score={stock.compositeScore} size="xs" />
                    </div>
                    <p className="mt-0.5 text-[10px] text-muted-foreground truncate max-w-[120px]">{stock.name}</p>
                  </div>
                  <Sparkline data={stock.priceHistory} width={64} height={24} strokeWidth={1.2} />
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="font-mono text-base font-semibold">${stock.price.toFixed(2)}</span>
                  <ChangeIndicator value={stock.changePct} className="text-[10px]" />
                </div>
                <ScoreBar score={stock.compositeScore} className="mt-2.5" />
                {stock.recommendation && (
                  <div className="mt-2 flex items-center justify-between">
                    <SignalBadge value={stock.recommendation} />
                    <RefreshIndicator ticker={stock.ticker} />
                  </div>
                )}
                {!stock.recommendation && (
                  <div className="mt-2 flex justify-end">
                    <RefreshIndicator ticker={stock.ticker} />
                  </div>
                )}
              </Link>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ======================== Sub-components ========================

function IndexCard({ data, index }: { data: IndexInfo; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.2 + index * 0.06 }}
      className="group flex items-center justify-between rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/30 hover:bg-hov cursor-pointer"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium">{data.name}</p>
        {data.value && (
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-xs text-foreground">{data.value.toLocaleString()}</span>
            <ChangeIndicator value={data.changePct ?? 0} className="text-[10px]" />
          </div>
        )}
        <p className="text-[10px] text-muted-foreground">{data.stockCount} stocks</p>
      </div>
      <div className="flex items-center gap-2">
        {data.sparkline && <Sparkline data={data.sparkline} width={56} height={22} strokeWidth={1} />}
        <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
      </div>
    </motion.div>
  );
}

function RecommendationRow({ rec, index }: { rec: Recommendation; index: number }) {
  const styles = {
    BUY: { icon: ArrowUpRight, bg: "bg-gain/10", text: "text-gain", border: "border-gain/20" },
    WATCH: { icon: Eye, bg: "bg-cyan/10", text: "text-cyan", border: "border-cyan/20" },
    AVOID: { icon: ArrowDownRight, bg: "bg-loss/10", text: "text-loss", border: "border-loss/20" },
    HOLD: { icon: Minus, bg: "bg-warning/10", text: "text-warning", border: "border-warning/20" },
    SELL: { icon: TrendingDown, bg: "bg-loss/10", text: "text-loss", border: "border-loss/20" },
  };
  const s = styles[rec.action];
  const Icon = s.icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: 0.35 + index * 0.05 }}
    >
      <Link
        to={`/stocks/${rec.ticker}`}
        className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/30 hover:bg-hov"
      >
        <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", s.bg)}>
          <Icon className={cn("h-4 w-4", s.text)} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold">{rec.ticker}</span>
            {MOCK_POSITIONS.some(p => p.ticker === rec.ticker) && (
              <span className="flex items-center gap-0.5 rounded bg-primary/10 px-1 py-0.5 text-[8px] font-semibold text-primary">
                <Briefcase className="h-2.5 w-2.5" /> Held
              </span>
            )}
            <span className={cn("rounded border px-1.5 py-0.5 text-[9px] font-semibold", s.bg, s.text, s.border)}>{rec.action}</span>
            <span className="text-[9px] text-muted-foreground">{rec.confidence}</span>
          </div>
          <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{rec.reasoning}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <RefreshIndicator ticker={rec.ticker} compact />
          <span className="font-mono text-sm font-semibold">{rec.compositeScore.toFixed(1)}</span>
        </div>
      </Link>
    </motion.div>
  );
}
