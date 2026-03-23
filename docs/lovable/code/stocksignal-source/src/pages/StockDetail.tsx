import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ScoreBadge } from "@/components/shared/ScoreBadge";
import { SignalBadge } from "@/components/shared/SignalBadge";
import { ScoreBar } from "@/components/shared/ScoreBar";
import { ChangeIndicator } from "@/components/shared/ChangeIndicator";
import { MOCK_FUNDAMENTALS, MOCK_DIVIDENDS, MOCK_INDEXES } from "@/lib/mock-data";
import { RefreshIndicator } from "@/components/shared/RefreshIndicator";
import { useStockRefresh } from "@/contexts/StockRefreshContext";
import { ChevronRight, Bookmark, BookmarkCheck, Check, X, ChevronDown, CandlestickChart, LineChart } from "lucide-react";
import { Area, AreaChart, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Line, ComposedChart, Bar, BarChart, Cell, ReferenceLine } from "recharts";

const TIMEFRAMES = ["1M", "3M", "6M", "1Y", "5Y"] as const;
type ChartType = "line" | "candle";

function generatePriceChart(base: number, days: number) {
  const data = [];
  let p = base * 0.85;
  for (let i = 0; i < days; i++) {
    const open = p;
    const change = (Math.random() - 0.48) * (base * 0.015);
    p += change;
    p = Math.max(p, 1);
    const high = Math.max(open, p) + Math.random() * (base * 0.005);
    const low = Math.min(open, p) - Math.random() * (base * 0.005);
    const d = new Date();
    d.setDate(d.getDate() - (days - i));
    data.push({
      date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      price: p,
      open,
      high,
      low,
      close: p,
      volume: Math.floor(Math.random() * 50000000 + 10000000),
    });
  }
  return data;
}

function generateBenchmarkData(days: number) {
  const sp = { base: 100, data: [] as number[] };
  const nq = { base: 100, data: [] as number[] };
  let spP = 100, nqP = 100;
  for (let i = 0; i < days; i++) {
    spP += (Math.random() - 0.48) * 0.8;
    nqP += (Math.random() - 0.47) * 1.0;
    sp.data.push(spP);
    nq.data.push(nqP);
  }
  return { sp: sp.data, nq: nq.data };
}

function generateSignalHistory(days: number) {
  const data = [];
  let score = 5 + Math.random() * 3;
  let rsi = 45 + Math.random() * 20;
  for (let i = 0; i < days; i++) {
    score = Math.max(0, Math.min(10, score + (Math.random() - 0.5) * 0.8));
    rsi = Math.max(0, Math.min(100, rsi + (Math.random() - 0.5) * 8));
    const d = new Date();
    d.setDate(d.getDate() - (days - i));
    data.push({
      date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      compositeScore: Math.round(score * 10) / 10,
      rsi: Math.round(rsi * 10) / 10,
    });
  }
  return data;
}

export default function StockDetail() {
  const { ticker } = useParams<{ ticker: string }>();
  const navigate = useNavigate();
  const { allStocks, stocks: stockMap } = useStockRefresh();
  const stock = stockMap.get(ticker || "") || allStocks[0];
  const [timeframe, setTimeframe] = useState<string>("1Y");
  const [chartType, setChartType] = useState<ChartType>("line");
  const [inWatchlist, setInWatchlist] = useState(true);
  const fundamentals = MOCK_FUNDAMENTALS[stock.ticker];
  const dividends = MOCK_DIVIDENDS[stock.ticker];
  const [showDivHistory, setShowDivHistory] = useState(false);

  const days = { "1M": 30, "3M": 90, "6M": 180, "1Y": 252, "5Y": 1260 }[timeframe] || 252;
  const priceData = generatePriceChart(stock.price, days);
  const signalHistory = generateSignalHistory(90);
  const benchmarks = generateBenchmarkData(days);

  // Normalize stock + benchmarks to percentage change for comparison
  const benchmarkData = priceData.map((d, i) => ({
    date: d.date,
    stock: ((d.price / priceData[0].price) - 1) * 100,
    sp500: ((benchmarks.sp[i] / benchmarks.sp[0]) - 1) * 100,
    nasdaq: ((benchmarks.nq[i] / benchmarks.nq[0]) - 1) * 100,
  }));

  return (
    <div className="p-6 space-y-6">
      {/* Close button */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 transition-colors mb-2"
        >
          <X className="h-3.5 w-3.5" />
          Close
        </button>
      </motion.div>

      {/* Breadcrumb + Header */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-3">
          <Link to="/" className="hover:text-foreground transition-colors">Dashboard</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="text-foreground font-medium">{stock.ticker}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="font-mono text-2xl font-bold">{stock.ticker}</h1>
            <ScoreBadge score={stock.compositeScore} />
            <span className="text-sm text-muted-foreground">{stock.name}</span>
            <span className="rounded bg-card2 px-2 py-0.5 text-[10px] text-muted-foreground">{stock.sector}</span>
          </div>
          <button
            onClick={() => setInWatchlist(!inWatchlist)}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all border",
              inWatchlist
                ? "bg-primary/10 text-primary border-primary/25"
                : "bg-card2 text-muted-foreground border-border hover:text-foreground"
            )}
          >
            {inWatchlist ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
            {inWatchlist ? "In Watchlist" : "Add to Watchlist"}
          </button>
        </div>
        <div className="flex items-baseline gap-2 mt-1">
          <span className="font-mono text-3xl font-bold">${stock.price.toFixed(2)}</span>
          <ChangeIndicator value={stock.changePct} className="text-sm" />
          <span className="text-xs text-muted-foreground">({stock.change >= 0 ? "+" : ""}${stock.change.toFixed(2)})</span>
          <RefreshIndicator ticker={stock.ticker} className="ml-2" />
        </div>
      </motion.div>

      {/* Price Chart */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-lg border border-border bg-card p-4"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-widest">Price History</h2>
          <div className="flex items-center gap-3">
            {/* Chart type toggle */}
            <div className="flex gap-0.5 rounded-lg bg-card2 p-0.5">
              <button
                onClick={() => setChartType("line")}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors",
                  chartType === "line" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <LineChart className="h-3 w-3" />
                Line
              </button>
              <button
                onClick={() => setChartType("candle")}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors",
                  chartType === "candle" ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <CandlestickChart className="h-3 w-3" />
                Candle
              </button>
            </div>
            {/* Timeframe */}
            <div className="flex gap-0.5 rounded-lg bg-card2 p-0.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
                    timeframe === tf ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
        </div>

        {chartType === "line" ? (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={priceData}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(187, 82%, 54%)" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="hsl(187, 82%, 54%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 25%, 17%)" />
              <XAxis dataKey="date" stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
              <YAxis stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ backgroundColor: "hsl(226, 30%, 16%)", border: "1px solid hsl(217, 25%, 17%)", borderRadius: 8, fontSize: 11 }} labelStyle={{ color: "hsl(215, 16%, 47%)" }} />
              <Area type="monotone" dataKey="price" stroke="hsl(187, 82%, 54%)" strokeWidth={1.5} fill="url(#priceGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={priceData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 25%, 17%)" />
              <XAxis dataKey="date" stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
              <YAxis stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ backgroundColor: "hsl(226, 30%, 16%)", border: "1px solid hsl(217, 25%, 17%)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "hsl(215, 16%, 47%)" }}
                formatter={(value: number, name: string) => [`$${value.toFixed(2)}`, name.charAt(0).toUpperCase() + name.slice(1)]}
              />
              <Bar dataKey="high" fill="transparent" />
              {priceData.map((entry, idx) => {
                const bullish = entry.close >= entry.open;
                return (
                  <ReferenceLine
                    key={`wick-${idx}`}
                    segment={[]}
                    stroke="none"
                  />
                );
              })}
              <Bar dataKey="close" barSize={6}>
                {priceData.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={entry.close >= entry.open ? "hsl(142, 71%, 45%)" : "hsl(0, 84%, 60%)"}
                  />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </motion.div>

      {/* Benchmark Comparison */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="rounded-lg border border-border bg-card p-4"
      >
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-widest mb-2">vs. Benchmarks (% Change)</h2>
        <div className="flex gap-4 text-[10px] mb-3">
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-primary" /> {stock.ticker}</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: "hsl(142, 71%, 45%)" }} /> S&P 500</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: "hsl(38, 92%, 50%)" }} /> NASDAQ</span>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={benchmarkData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 25%, 17%)" />
            <XAxis dataKey="date" stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`} />
            <Tooltip
              contentStyle={{ backgroundColor: "hsl(226, 30%, 16%)", border: "1px solid hsl(217, 25%, 17%)", borderRadius: 8, fontSize: 11 }}
              formatter={(value: number, name: string) => [`${value > 0 ? "+" : ""}${value.toFixed(1)}%`, name === "stock" ? stock.ticker : name === "sp500" ? "S&P 500" : "NASDAQ"]}
            />
            <ReferenceLine y={0} stroke="hsl(215, 16%, 47%)" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="stock" stroke="hsl(187, 82%, 54%)" strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="sp500" stroke="hsl(142, 71%, 45%)" strokeWidth={1} dot={false} strokeDasharray="4 2" />
            <Line type="monotone" dataKey="nasdaq" stroke="hsl(38, 92%, 50%)" strokeWidth={1} dot={false} strokeDasharray="4 2" />
          </ComposedChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Signal Breakdown */}
      <section>
        <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Signal Breakdown</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <SignalCard title="RSI (14)" value={stock.rsiValue.toFixed(1)} signal={stock.rsiSignal} description={`${stock.rsiSignal === "OVERSOLD" ? "Below 30 — potential buying opportunity" : stock.rsiSignal === "OVERBOUGHT" ? "Above 70 — may be overextended" : "Between 30-70 — balanced momentum"}`} meter={stock.rsiValue / 100} delay={0.2} />
          <SignalCard title="MACD" value={stock.macdValue.toFixed(2)} signal={stock.macdSignal} description={stock.macdSignal === "BULLISH" ? "Histogram positive — upward momentum" : "Histogram negative — downward pressure"} delay={0.25} />
          <SignalCard title="SMA Crossover" value="" signal={stock.smaSignal} description={
            stock.smaSignal === "GOLDEN_CROSS" ? "50-day crossed above 200-day" :
            stock.smaSignal === "DEATH_CROSS" ? "50-day crossed below 200-day" :
            stock.smaSignal === "ABOVE_200" ? "Price above 200-day SMA" : "Price below 200-day SMA"
          } delay={0.3} />
          <SignalCard title="Bollinger" value="" signal={stock.bbPosition} description={
            stock.bbPosition === "UPPER" ? "Near upper band — potentially overbought" :
            stock.bbPosition === "LOWER" ? "Near lower band — potentially oversold" : "Within normal range"
          } delay={0.35} />
        </div>
      </section>

      {/* Signal History Chart */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="rounded-lg border border-border bg-card p-4"
      >
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-widest mb-4">Signal History (90 days)</h2>
        <div className="flex gap-4 text-[10px] mb-2">
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-primary" /> Composite Score</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-warning" /> RSI</span>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={signalHistory}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 25%, 17%)" />
            <XAxis dataKey="date" stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis yAxisId="left" domain={[0, 10]} stroke="hsl(187, 82%, 54%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis yAxisId="right" orientation="right" domain={[0, 100]} stroke="hsl(38, 92%, 50%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ backgroundColor: "hsl(226, 30%, 16%)", border: "1px solid hsl(217, 25%, 17%)", borderRadius: 8, fontSize: 11 }} />
            <Line yAxisId="left" type="monotone" dataKey="compositeScore" stroke="hsl(187, 82%, 54%)" strokeWidth={1.5} dot={false} />
            <Line yAxisId="right" type="monotone" dataKey="rsi" stroke="hsl(38, 92%, 50%)" strokeWidth={1} dot={false} strokeDasharray="4 2" />
          </ComposedChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Risk & Return */}
      <section>
        <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Risk & Return</h2>
        <div className="grid grid-cols-3 gap-3">
          <MetricCard label="Annual Return" value={`${stock.annualReturn >= 0 ? "+" : ""}${stock.annualReturn.toFixed(1)}%`} positive={stock.annualReturn >= 0} delay={0.35} />
          <MetricCard label="Volatility" value={`${stock.volatility.toFixed(1)}%`} neutral delay={0.4} />
          <MetricCard label="Sharpe Ratio" value={stock.sharpe.toFixed(2)} positive={stock.sharpe >= 1} negative={stock.sharpe < 0} delay={0.45} />
        </div>
      </section>

      {/* Fundamentals */}
      {fundamentals && (
        <section>
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Fundamentals</h2>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 mb-4">
            <MetricCard label="P/E Ratio" value={fundamentals.pe.toFixed(1)} delay={0.5} />
            <MetricCard label="PEG Ratio" value={fundamentals.peg.toFixed(1)} positive={fundamentals.peg < 1} delay={0.52} />
            <MetricCard label="FCF Yield" value={`${fundamentals.fcfYield.toFixed(1)}%`} positive={fundamentals.fcfYield > 5} delay={0.54} />
            <MetricCard label="Debt/Equity" value={fundamentals.debtEquity.toFixed(2)} positive={fundamentals.debtEquity < 1} delay={0.56} />
          </div>

          {/* Piotroski */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.58 }}
            className="rounded-lg border border-border bg-card p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-medium">Piotroski F-Score</h3>
              <span className={cn(
                "font-mono text-lg font-bold",
                fundamentals.piotroski >= 7 ? "text-gain" : fundamentals.piotroski >= 4 ? "text-warning" : "text-loss"
              )}>
                {fundamentals.piotroski}/9
              </span>
            </div>
            <div className="flex gap-0.5 mb-3">
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className={cn("h-2 flex-1 rounded-sm", i < fundamentals.piotroski ? "bg-gain" : "bg-muted/50")} />
              ))}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {fundamentals.piotroskiBreakdown.map((item) => (
                <div key={item.name} className="flex items-center gap-1.5 text-[10px]">
                  {item.passed ? <Check className="h-3 w-3 text-gain shrink-0" /> : <X className="h-3 w-3 text-loss shrink-0" />}
                  <span className={item.passed ? "text-foreground" : "text-muted-foreground"}>{item.name}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </section>
      )}

      {/* Dividends */}
      {dividends && (
        <section>
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-3">Dividends</h2>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 mb-3">
            <MetricCard label="Yield" value={`${dividends.yield.toFixed(2)}%`} delay={0.6} />
            <MetricCard label="Annual Dividends" value={`$${dividends.annualDividends.toFixed(2)}`} delay={0.62} />
            <MetricCard label="Total Received" value={`$${dividends.totalReceived.toFixed(2)}`} delay={0.64} />
            <MetricCard label="Payment Count" value={String(dividends.paymentCount)} delay={0.66} />
          </div>
          <button
            onClick={() => setShowDivHistory(!showDivHistory)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronDown className={cn("h-3 w-3 transition-transform", showDivHistory && "rotate-180")} />
            Payment History
          </button>
          {showDivHistory && (
            <div className="mt-2 rounded-lg border border-border overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-card2">
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 text-left text-[10px] text-muted-foreground">Date</th>
                    <th className="px-3 py-2 text-right text-[10px] text-muted-foreground">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {dividends.history.map((h) => (
                    <tr key={h.date} className="border-b border-border/50">
                      <td className="px-3 py-2 font-mono">{h.date}</td>
                      <td className="px-3 py-2 text-right font-mono text-gain">${h.amount.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ======================== Sub-components ========================

function SignalCard({ title, value, signal, description, meter, delay = 0 }: {
  title: string; value: string; signal: string; description: string; meter?: number; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="rounded-lg border border-border bg-card p-4"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{title}</span>
        <SignalBadge value={signal} />
      </div>
      {value && <p className="font-mono text-xl font-semibold">{value}</p>}
      {meter !== undefined && (
        <div className="mt-2 h-1.5 rounded-full bg-muted/50 overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all", meter < 0.3 ? "bg-gain" : meter > 0.7 ? "bg-loss" : "bg-warning")}
            style={{ width: `${meter * 100}%` }}
          />
        </div>
      )}
      <p className="mt-2 text-[10px] text-muted-foreground leading-relaxed">{description}</p>
    </motion.div>
  );
}

function MetricCard({ label, value, positive, negative, neutral, delay = 0 }: {
  label: string; value: string; positive?: boolean; negative?: boolean; neutral?: boolean; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="rounded-lg border border-border bg-card p-4"
    >
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
      <p className={cn(
        "mt-1 font-mono text-lg font-semibold",
        positive ? "text-gain" : negative ? "text-loss" : "text-foreground"
      )}>
        {value}
      </p>
    </motion.div>
  );
}
