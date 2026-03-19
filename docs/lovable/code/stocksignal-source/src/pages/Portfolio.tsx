import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { AllocationDonut } from "@/components/shared/AllocationDonut";
import { ChangeIndicator } from "@/components/shared/ChangeIndicator";
import { useChat } from "@/contexts/ChatContext";
import { MOCK_POSITIONS, MOCK_TRANSACTIONS, MOCK_SECTORS, type Position, type Transaction } from "@/lib/mock-data";
import { Settings, Plus, ChevronDown, AlertTriangle, AlertOctagon, Trash2, X } from "lucide-react";
import { Area, AreaChart, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

function generatePortfolioHistory(): { date: string; value: number; costBasis: number }[] {
  const data = [];
  let val = 6400, cost = 6355;
  for (let i = 90; i >= 0; i--) {
    val += (Math.random() - 0.55) * 80;
    const d = new Date(); d.setDate(d.getDate() - i);
    data.push({ date: d.toLocaleDateString("en-US", { month: "short", day: "numeric" }), value: Math.max(val, 100), costBasis: cost });
  }
  return data;
}

const portfolioHistory = generatePortfolioHistory();

// Portfolio summary from mock positions
const totalValue = MOCK_POSITIONS.reduce((s, p) => s + p.marketValue, 0);
const totalCost = MOCK_POSITIONS.reduce((s, p) => s + p.avgCost * p.shares, 0);
const totalPnl = totalValue - totalCost;
const totalPnlPct = (totalPnl / totalCost) * 100;

export default function Portfolio() {
  const { chatOpen } = useChat();
  const isNarrow = chatOpen;
  const [showSettings, setShowSettings] = useState(false);
  const [showTransactions, setShowTransactions] = useState(false);
  const [showLogTx, setShowLogTx] = useState(false);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Portfolio</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowSettings(true)} className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <Settings className="h-3.5 w-3.5" /> Settings
          </button>
          <button onClick={() => setShowLogTx(true)} className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
            <Plus className="h-3.5 w-3.5" /> Log Transaction
          </button>
        </div>
      </motion.div>

      {/* KPI tiles */}
      <div className={cn("grid grid-cols-2 gap-3 transition-all duration-300", isNarrow ? "lg:grid-cols-2 xl:grid-cols-4" : "lg:grid-cols-4")}>
        <KpiTile label="Total Value" value={`$${totalValue.toFixed(2)}`} accent="cyan" />
        <KpiTile label="Cost Basis" value={`$${totalCost.toFixed(2)}`} />
        <KpiTile label="Unrealized P&L" value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`} change={totalPnl >= 0 ? "gain" : "loss"} accent={totalPnl >= 0 ? "gain" : "loss"} />
        <KpiTile label="Return" value={`${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(2)}%`} change={totalPnlPct >= 0 ? "gain" : "loss"} accent={totalPnlPct >= 0 ? "gain" : "loss"} />
      </div>

      {/* Value History */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-widest mb-4">Portfolio Value Over Time</h2>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={portfolioHistory}>
            <defs>
              <linearGradient id="valGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(187, 82%, 54%)" stopOpacity={0.15} />
                <stop offset="95%" stopColor="hsl(187, 82%, 54%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 25%, 17%)" />
            <XAxis dataKey="date" stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis stroke="hsl(215, 16%, 47%)" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ backgroundColor: "hsl(226, 30%, 16%)", border: "1px solid hsl(217, 25%, 17%)", borderRadius: 8, fontSize: 11 }} />
            <Area type="monotone" dataKey="value" stroke="hsl(187, 82%, 54%)" strokeWidth={1.5} fill="url(#valGrad)" />
            <Area type="monotone" dataKey="costBasis" stroke="hsl(215, 16%, 47%)" strokeWidth={1} strokeDasharray="4 2" fill="none" />
          </AreaChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Two columns: Positions + Allocation */}
      <div className={cn("grid grid-cols-1 gap-6 transition-all duration-300", isNarrow ? "lg:grid-cols-1 xl:grid-cols-5" : "lg:grid-cols-5")}>
        <div className={cn(isNarrow ? "xl:col-span-3" : "lg:col-span-3", "space-y-4")}>
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">Positions</h2>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-card2">
                <tr className="border-b border-border">
                  {["Ticker", "Shares", "Avg Cost", "Current", "Market Val", "P&L", "Return", "Weight", "Alerts"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {MOCK_POSITIONS.map((pos) => (
                  <tr key={pos.ticker} className="border-b border-border/50 hover:bg-hov transition-colors">
                    <td className="px-3 py-2.5 font-mono font-bold">{pos.ticker}</td>
                    <td className="px-3 py-2.5 font-mono">{pos.shares}</td>
                    <td className="px-3 py-2.5 font-mono">${pos.avgCost.toFixed(2)}</td>
                    <td className="px-3 py-2.5 font-mono">${pos.currentPrice.toFixed(2)}</td>
                    <td className="px-3 py-2.5 font-mono">${pos.marketValue.toFixed(2)}</td>
                    <td className="px-3 py-2.5"><ChangeIndicator value={pos.unrealizedPnl} prefix="$" suffix="" className="text-xs" /></td>
                    <td className="px-3 py-2.5"><ChangeIndicator value={pos.unrealizedPnlPct} className="text-xs" /></td>
                    <td className="px-3 py-2.5 font-mono">{pos.weight.toFixed(1)}%</td>
                    <td className="px-3 py-2.5">
                      <div className="flex gap-1">
                        {pos.alerts.map((a, i) => (
                          <span
                            key={i}
                            title={a.message}
                            className={cn(
                              "flex h-5 w-5 items-center justify-center rounded",
                              a.severity === "critical" ? "bg-loss/15 text-loss" : "bg-warning/15 text-warning"
                            )}
                          >
                            {a.severity === "critical" ? <AlertOctagon className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Transactions */}
          <button onClick={() => setShowTransactions(!showTransactions)} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <ChevronDown className={cn("h-3 w-3 transition-transform", showTransactions && "rotate-180")} />
            Transaction History
          </button>
          {showTransactions && (
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-card2">
                  <tr className="border-b border-border">
                    {["Date", "Ticker", "Type", "Shares", "Price", "Total", ""].map((h) => (
                      <th key={h} className="px-3 py-2 text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {MOCK_TRANSACTIONS.map((tx) => (
                    <tr key={tx.id} className="border-b border-border/50 hover:bg-hov transition-colors">
                      <td className="px-3 py-2 font-mono">{tx.date}</td>
                      <td className="px-3 py-2 font-mono font-bold">{tx.ticker}</td>
                      <td className="px-3 py-2">
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", tx.type === "BUY" ? "bg-gain/15 text-gain" : "bg-loss/15 text-loss")}>{tx.type}</span>
                      </td>
                      <td className="px-3 py-2 font-mono">{tx.shares}</td>
                      <td className="px-3 py-2 font-mono">${tx.pricePerShare.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono">${tx.total.toFixed(2)}</td>
                      <td className="px-3 py-2">
                        <button className="text-muted-foreground hover:text-loss transition-colors"><Trash2 className="h-3 w-3" /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Sector Allocation */}
        <div className={cn(isNarrow ? "xl:col-span-2" : "lg:col-span-2")}>
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mb-4">Sector Allocation</h2>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="rounded-lg border border-border bg-card p-4">
            <AllocationDonut sectors={MOCK_SECTORS} size={120} />
            <div className="mt-4 flex items-center gap-1.5 rounded-md bg-loss/10 border border-loss/20 px-3 py-2 text-[10px] text-loss">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              Technology exceeds 30% sector limit (100%)
            </div>
          </motion.div>

          {/* Rebalancing */}
          <h2 className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest mt-6 mb-3">Rebalancing</h2>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="rounded-lg border border-border bg-card p-4 space-y-3">
            {MOCK_POSITIONS.map((p) => (
              <div key={p.ticker} className="flex items-center justify-between text-xs">
                <span className="font-mono font-bold w-12">{p.ticker}</span>
                <span className="font-mono text-muted-foreground">{p.weight.toFixed(1)}%</span>
                <span className="text-muted-foreground">→</span>
                <span className="font-mono">50.0%</span>
                <span className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium",
                  p.weight > 50 ? "bg-warning/15 text-warning" : "bg-gain/15 text-gain"
                )}>
                  {p.weight > 50 ? "AT_CAP" : "BUY_MORE"}
                </span>
              </div>
            ))}
            <p className="text-[9px] text-muted-foreground mt-2">Targets based on equal-weight across {MOCK_POSITIONS.length} positions</p>
          </motion.div>
        </div>
      </div>

      {/* Settings Sheet */}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-background/60 backdrop-blur-sm" onClick={() => setShowSettings(false)} />
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            className="w-80 bg-card border-l border-border p-6 space-y-6"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Portfolio Settings</h2>
              <button onClick={() => setShowSettings(false)} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
            </div>
            <SettingSlider label="Stop-loss threshold" value={20} suffix="%" />
            <SettingSlider label="Max position concentration" value={5} suffix="%" />
            <SettingSlider label="Max sector concentration" value={30} suffix="%" />
            <button className="w-full rounded-lg bg-primary py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors">Save</button>
          </motion.div>
        </div>
      )}

      {/* Log Transaction Modal */}
      {showLogTx && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-sm" onClick={() => setShowLogTx(false)}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="w-96 rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Log Transaction</h2>
              <button onClick={() => setShowLogTx(false)} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
            </div>
            <div className="space-y-3">
              <ModalInput label="Ticker" placeholder="AAPL" />
              <div className="flex gap-2">
                <button className="flex-1 rounded-lg bg-gain/15 border border-gain/25 py-2 text-xs font-semibold text-gain">BUY</button>
                <button className="flex-1 rounded-lg bg-card2 border border-border py-2 text-xs font-semibold text-muted-foreground hover:text-loss hover:bg-loss/10 hover:border-loss/25 transition-colors">SELL</button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <ModalInput label="Shares" placeholder="10" type="number" />
                <ModalInput label="Price per share" placeholder="195.50" type="number" />
              </div>
              <ModalInput label="Date" type="date" />
              <ModalInput label="Notes" placeholder="Optional notes..." />
            </div>
            <button className="w-full rounded-lg bg-primary py-2.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors">Submit</button>
          </motion.div>
        </div>
      )}
    </div>
  );
}

// ======================== Sub-components ========================

function KpiTile({ label, value, change, accent }: { label: string; value: string; change?: string; accent?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-lg border border-border bg-card p-4">
      <div className={cn(
        "absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r",
        accent === "cyan" ? "from-primary to-primary/0" :
        accent === "gain" ? "from-gain to-gain/0" :
        accent === "loss" ? "from-loss to-loss/0" : "from-muted to-muted/0"
      )} />
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-1 font-mono text-xl font-semibold", change === "gain" ? "text-gain" : change === "loss" ? "text-loss" : "text-foreground")}>
        {value}
      </p>
    </motion.div>
  );
}

function SettingSlider({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="font-mono text-xs">{value}{suffix}</span>
      </div>
      <input type="range" min={1} max={100} defaultValue={value} className="w-full accent-primary h-1" />
    </div>
  );
}

function ModalInput({ label, placeholder, type = "text" }: { label: string; placeholder?: string; type?: string }) {
  return (
    <div>
      <label className="text-[10px] text-muted-foreground mb-1 block">{label}</label>
      <input
        type={type}
        placeholder={placeholder}
        className="w-full rounded-lg border border-border bg-card2 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      />
    </div>
  );
}
