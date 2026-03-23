// ===================== Types =====================

export interface IndexInfo {
  name: string;
  slug: string;
  stockCount: number;
  description: string;
  value?: number;
  changePct?: number;
  sparkline?: number[];
}

export interface WatchlistStock {
  ticker: string;
  name: string;
  sector: string;
  price: number;
  change: number;
  changePct: number;
  compositeScore: number;
  rsiValue: number;
  rsiSignal: "OVERSOLD" | "NEUTRAL" | "OVERBOUGHT";
  macdValue: number;
  macdSignal: "BULLISH" | "BEARISH";
  smaSignal: "GOLDEN_CROSS" | "ABOVE_200" | "BELOW_200" | "DEATH_CROSS";
  bbPosition: "UPPER" | "MIDDLE" | "LOWER";
  annualReturn: number;
  volatility: number;
  sharpe: number;
  priceHistory: number[];
  recommendation?: "BUY" | "WATCH" | "AVOID";
}

export interface StatTileData {
  label: string;
  value: string;
  subValue?: string;
  change?: string;
  changeType?: "gain" | "loss" | "neutral";
  accent?: "cyan" | "gain" | "loss" | "warning";
  type?: "donut" | "signal-summary";
}

export interface SectorAllocation {
  sector: string;
  pct: number;
  color: string;
  overLimit?: boolean;
}

export interface Recommendation {
  ticker: string;
  action: "BUY" | "WATCH" | "AVOID" | "HOLD" | "SELL";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  compositeScore: number;
  reasoning: string;
}

export interface Position {
  ticker: string;
  name: string;
  sector: string;
  shares: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  weight: number;
  alerts: PositionAlert[];
}

export interface PositionAlert {
  type: "stop_loss" | "position_concentration" | "sector_concentration" | "weak_fundamentals";
  severity: "critical" | "warning";
  message: string;
}

export interface Transaction {
  id: string;
  ticker: string;
  type: "BUY" | "SELL";
  shares: number;
  pricePerShare: number;
  total: number;
  date: string;
  notes?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  timestamp: Date;
}

export interface ToolCall {
  id: string;
  name: string;
  status: "running" | "completed" | "error";
  params?: Record<string, unknown>;
  result?: string;
  error?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  agentType: "stock" | "general";
  lastMessage: string;
  createdAt: Date;
  expired?: boolean;
}

export interface FundamentalData {
  pe: number;
  peg: number;
  fcfYield: number;
  debtEquity: number;
  piotroski: number;
  piotroskiBreakdown: { name: string; passed: boolean }[];
}

export interface DividendData {
  yield: number;
  annualDividends: number;
  totalReceived: number;
  paymentCount: number;
  history: { date: string; amount: number }[];
}

// ===================== Helpers =====================

export function spark(base: number, volatility: number, trend: number, n = 30): number[] {
  const pts: number[] = [];
  let p = base;
  for (let i = 0; i < n; i++) {
    p += (Math.random() - 0.5 + trend * 0.02) * volatility;
    pts.push(Math.max(p, 1));
  }
  return pts;
}

/** Simulate refreshing a stock's live data — returns a new object with updated price/change/signals/sparkline */
export function simulateStockRefresh(stock: WatchlistStock): WatchlistStock {
  const priceDelta = (Math.random() - 0.48) * stock.price * 0.02;
  const newPrice = Math.max(stock.price + priceDelta, 1);
  const change = +(priceDelta).toFixed(2);
  const changePct = +((priceDelta / stock.price) * 100).toFixed(2);
  const newRsi = Math.max(5, Math.min(95, stock.rsiValue + (Math.random() - 0.5) * 6));
  const rsiSignal: WatchlistStock["rsiSignal"] = newRsi < 30 ? "OVERSOLD" : newRsi > 70 ? "OVERBOUGHT" : "NEUTRAL";
  const newMacd = +(stock.macdValue + (Math.random() - 0.5) * 0.5).toFixed(2);
  const macdSignal: WatchlistStock["macdSignal"] = newMacd >= 0 ? "BULLISH" : "BEARISH";
  const newScore = Math.max(0, Math.min(10, +(stock.compositeScore + (Math.random() - 0.5) * 0.4).toFixed(1)));
  return {
    ...stock,
    price: +newPrice.toFixed(2),
    change,
    changePct,
    compositeScore: newScore,
    rsiValue: +newRsi.toFixed(1),
    rsiSignal,
    macdValue: newMacd,
    macdSignal,
    priceHistory: spark(newPrice, newPrice * 0.01, changePct > 0 ? 0.5 : -0.5),
  };
}

// ===================== Mock Data =====================

export const MOCK_INDEXES: IndexInfo[] = [
  { name: "S&P 500", slug: "sp500", stockCount: 503, description: "Large-cap US equities", value: 5321.40, changePct: 0.82, sparkline: spark(5300, 15, 1) },
  { name: "NASDAQ-100", slug: "nasdaq100", stockCount: 101, description: "Top 100 NASDAQ stocks", value: 18672.10, changePct: 1.15, sparkline: spark(18500, 50, 1) },
  { name: "Dow 30", slug: "dow30", stockCount: 30, description: "Blue-chip industrials", value: 39412.80, changePct: -0.23, sparkline: spark(39500, 80, -0.5) },
];

export const MOCK_STATS: StatTileData[] = [
  { label: "Portfolio Value", value: "$3,370.15", change: "↑ $524.30", changeType: "gain", accent: "cyan" },
  { label: "Unrealized P&L", value: "-$2,984.85", change: "-46.97%", changeType: "loss", accent: "loss" },
  { label: "Signals", value: "5 Buy", subValue: "0 Hold · 0 Sell", changeType: "gain", accent: "gain", type: "signal-summary" },
  { label: "Top Signal", value: "GOOGL", subValue: "Score 4.1", accent: "cyan" },
  { label: "Allocation", value: "", accent: "warning", type: "donut" },
];

export const MOCK_SECTORS: SectorAllocation[] = [
  { sector: "Technology", pct: 100, color: "hsl(187, 82%, 54%)", overLimit: true },
];

export const MOCK_SECTORS_FULL: SectorAllocation[] = [
  { sector: "Technology", pct: 42, color: "hsl(187, 82%, 54%)" },
  { sector: "Healthcare", pct: 18, color: "hsl(142, 71%, 45%)" },
  { sector: "Financials", pct: 15, color: "hsl(38, 92%, 50%)" },
  { sector: "Consumer", pct: 13, color: "hsl(280, 65%, 55%)" },
  { sector: "Energy", pct: 12, color: "hsl(0, 84%, 60%)" },
];

const ALL_STOCKS: WatchlistStock[] = [
  { ticker: "AAPL", name: "Apple Inc.", sector: "Technology", price: 247.93, change: 3.42, changePct: 1.40, compositeScore: 3.1, rsiValue: 55.2, rsiSignal: "NEUTRAL", macdValue: 0.82, macdSignal: "BEARISH", smaSignal: "ABOVE_200", bbPosition: "MIDDLE", annualReturn: 28.3, volatility: 22.1, sharpe: 1.15, priceHistory: spark(245, 3, 0.5), recommendation: "WATCH" },
  { ticker: "MSFT", name: "Microsoft Corp.", sector: "Technology", price: 387.34, change: 5.18, changePct: 1.35, compositeScore: 3.4, rsiValue: 48.6, rsiSignal: "NEUTRAL", macdValue: 1.24, macdSignal: "BULLISH", smaSignal: "ABOVE_200", bbPosition: "MIDDLE", annualReturn: 22.7, volatility: 24.8, sharpe: 0.85, priceHistory: spark(385, 4, 0.3), recommendation: "WATCH" },
  { ticker: "NVDA", name: "NVIDIA Corp.", sector: "Technology", price: 178.17, change: -12.35, changePct: -6.48, compositeScore: 3.4, rsiValue: 38.1, rsiSignal: "NEUTRAL", macdValue: -2.15, macdSignal: "BEARISH", smaSignal: "BELOW_200", bbPosition: "LOWER", annualReturn: -15.2, volatility: 55.3, sharpe: -0.35, priceHistory: spark(190, 8, -1.5), recommendation: "AVOID" },
  { ticker: "GOOGL", name: "Alphabet Inc.", sector: "Technology", price: 305.57, change: 2.85, changePct: 0.94, compositeScore: 4.1, rsiValue: 52.8, rsiSignal: "NEUTRAL", macdValue: 1.56, macdSignal: "BULLISH", smaSignal: "ABOVE_200", bbPosition: "MIDDLE", annualReturn: 32.1, volatility: 26.4, sharpe: 1.12, priceHistory: spark(303, 3, 0.6), recommendation: "BUY" },
  { ticker: "TSLA", name: "Tesla Inc.", sector: "Technology", price: 379.34, change: -8.50, changePct: -2.19, compositeScore: 2.6, rsiValue: 62.3, rsiSignal: "NEUTRAL", macdValue: -3.20, macdSignal: "BEARISH", smaSignal: "BELOW_200", bbPosition: "MIDDLE", annualReturn: -8.5, volatility: 62.1, sharpe: -0.21, priceHistory: spark(385, 12, -1), recommendation: "AVOID" },
  { ticker: "AMZN", name: "Amazon.com Inc.", sector: "Consumer", price: 186.42, change: -1.23, changePct: -0.66, compositeScore: 6.4, rsiValue: 44.2, rsiSignal: "NEUTRAL", macdValue: 0.45, macdSignal: "BULLISH", smaSignal: "ABOVE_200", bbPosition: "MIDDLE", annualReturn: 18.9, volatility: 30.2, sharpe: 0.55, priceHistory: spark(187, 3, -0.2), recommendation: "WATCH" },
  { ticker: "META", name: "Meta Platforms", sector: "Technology", price: 512.30, change: 8.40, changePct: 1.67, compositeScore: 8.1, rsiValue: 61.5, rsiSignal: "NEUTRAL", macdValue: 3.82, macdSignal: "BULLISH", smaSignal: "GOLDEN_CROSS", bbPosition: "UPPER", annualReturn: 45.2, volatility: 32.1, sharpe: 1.32, priceHistory: spark(505, 6, 1.2), recommendation: "BUY" },
  { ticker: "JPM", name: "JPMorgan Chase", sector: "Financials", price: 198.45, change: -0.82, changePct: -0.41, compositeScore: 5.8, rsiValue: 50.1, rsiSignal: "NEUTRAL", macdValue: -0.35, macdSignal: "BEARISH", smaSignal: "ABOVE_200", bbPosition: "MIDDLE", annualReturn: 15.3, volatility: 20.5, sharpe: 0.65, priceHistory: spark(199, 2, -0.1), recommendation: "WATCH" },
  { ticker: "UNH", name: "UnitedHealth Group", sector: "Healthcare", price: 528.15, change: 6.22, changePct: 1.19, compositeScore: 4.2, rsiValue: 32.8, rsiSignal: "NEUTRAL", macdValue: -1.85, macdSignal: "BEARISH", smaSignal: "BELOW_200", bbPosition: "LOWER", annualReturn: -5.2, volatility: 28.3, sharpe: -0.25, priceHistory: spark(525, 5, -0.5), recommendation: "AVOID" },
  { ticker: "XOM", name: "Exxon Mobil", sector: "Energy", price: 104.38, change: -2.15, changePct: -2.02, compositeScore: 3.5, rsiValue: 28.5, rsiSignal: "OVERSOLD", macdValue: -1.92, macdSignal: "BEARISH", smaSignal: "DEATH_CROSS", bbPosition: "LOWER", annualReturn: -12.1, volatility: 25.8, sharpe: -0.55, priceHistory: spark(106, 3, -1), recommendation: "AVOID" },
];

export const MOCK_WATCHLIST: WatchlistStock[] = ALL_STOCKS.slice(0, 5);
export const MOCK_ALL_STOCKS: WatchlistStock[] = ALL_STOCKS;

export const MOCK_RECOMMENDATIONS: Recommendation[] = [
  { ticker: "GOOGL", action: "BUY", confidence: "MEDIUM", compositeScore: 4.1, reasoning: "Strongest composite score in watchlist. Bullish MACD with stable RSI." },
  { ticker: "META", action: "BUY", confidence: "MEDIUM", compositeScore: 8.1, reasoning: "Golden cross formation with strong bullish momentum across indicators." },
  { ticker: "MSFT", action: "WATCH", confidence: "LOW", compositeScore: 3.4, reasoning: "Mixed signals — bullish MACD but below-average composite." },
  { ticker: "NVDA", action: "AVOID", confidence: "MEDIUM", compositeScore: 3.4, reasoning: "Below 200-day SMA, bearish MACD. High volatility risk." },
  { ticker: "TSLA", action: "AVOID", confidence: "HIGH", compositeScore: 2.6, reasoning: "Weakest score. Bearish across all indicators." },
];

export const MOCK_POSITIONS: Position[] = [
  {
    ticker: "AAPL", name: "Apple Inc.", sector: "Technology", shares: 10,
    avgCost: 195.50, currentPrice: 247.93, marketValue: 2479.30,
    unrealizedPnl: 524.30, unrealizedPnlPct: 26.82, weight: 73.6,
    alerts: [
      { type: "position_concentration", severity: "critical", message: "Position exceeds 5% limit (73.6%)" },
      { type: "sector_concentration", severity: "warning", message: "Technology sector exceeds 30% limit" },
    ],
  },
  {
    ticker: "NVDA", name: "NVIDIA Corp.", sector: "Technology", shares: 5,
    avgCost: 880.00, currentPrice: 178.17, marketValue: 890.85,
    unrealizedPnl: -3509.15, unrealizedPnlPct: -79.75, weight: 26.4,
    alerts: [
      { type: "stop_loss", severity: "critical", message: "Trailing stop-loss triggered (-79.75%)" },
      { type: "position_concentration", severity: "critical", message: "Position exceeds 5% limit (26.4%)" },
    ],
  },
];

export const MOCK_TRANSACTIONS: Transaction[] = [
  { id: "t1", ticker: "AAPL", type: "BUY", shares: 10, pricePerShare: 195.50, total: 1955.00, date: "2024-06-15", notes: "Initial position" },
  { id: "t2", ticker: "NVDA", type: "BUY", shares: 5, pricePerShare: 880.00, total: 4400.00, date: "2024-03-10", notes: "Pre-earnings bet" },
];

export const MOCK_CHAT_SESSIONS: ChatSession[] = [
  { id: "s1", title: "Portfolio Analysis", agentType: "stock", lastMessage: "Your portfolio is heavily concentrated...", createdAt: new Date(Date.now() - 3600000) },
  { id: "s2", title: "NVDA Deep Dive", agentType: "stock", lastMessage: "NVIDIA's current signals show...", createdAt: new Date(Date.now() - 86400000) },
  { id: "s3", title: "Market Overview", agentType: "general", lastMessage: "Today's market is showing...", createdAt: new Date(Date.now() - 172800000), expired: true },
];

export const MOCK_CHAT_MESSAGES: ChatMessage[] = [
  {
    id: "m1", role: "user", content: "Analyze my portfolio",
    timestamp: new Date(Date.now() - 300000),
  },
  {
    id: "m2", role: "assistant",
    content: "Your portfolio is **heavily concentrated in Technology (100%)**. Here's a breakdown:\n\n| Ticker | Shares | P&L | Return |\n|--------|--------|-----|--------|\n| AAPL | 10 | +$524.30 | +26.8% |\n| NVDA | 5 | -$3,509.15 | -79.8% |\n\n**Key concerns:**\n1. **Position concentration** — AAPL is 73.6% of portfolio, far above the 5% target\n2. **Stop-loss breach** — NVDA has dropped 79.8%, well past the 20% trailing stop\n3. **Zero diversification** — 100% in Technology sector\n\nI'd recommend:\n- Consider trimming AAPL to reduce concentration risk\n- Evaluate whether to exit NVDA given the magnitude of the loss\n- Diversify into Healthcare, Financials, or Consumer sectors",
    toolCalls: [
      { id: "tc1", name: "get_portfolio_positions", status: "completed", result: "2 positions: AAPL (+26.8%), NVDA (-79.8%)" },
      { id: "tc2", name: "get_portfolio_summary", status: "completed", result: "Value: $3,370.15 | P&L: -$2,984.85 | Sectors: Technology 100%" },
    ],
    timestamp: new Date(Date.now() - 295000),
  },
];

export const MOCK_FUNDAMENTALS: Record<string, FundamentalData> = {
  AAPL: {
    pe: 28.5, peg: 1.2, fcfYield: 3.8, debtEquity: 1.45,
    piotroski: 7,
    piotroskiBreakdown: [
      { name: "Positive Net Income", passed: true },
      { name: "Positive Operating Cash Flow", passed: true },
      { name: "ROA Increasing", passed: true },
      { name: "Cash Flow > Net Income", passed: true },
      { name: "Debt Ratio Decreasing", passed: false },
      { name: "Current Ratio Increasing", passed: true },
      { name: "No New Shares Issued", passed: true },
      { name: "Gross Margin Increasing", passed: false },
      { name: "Asset Turnover Increasing", passed: true },
    ],
  },
};

export const MOCK_DIVIDENDS: Record<string, DividendData> = {
  AAPL: {
    yield: 0.52, annualDividends: 0.96, totalReceived: 4.80, paymentCount: 5,
    history: [
      { date: "2025-02-07", amount: 0.24 },
      { date: "2024-11-08", amount: 0.24 },
      { date: "2024-08-09", amount: 0.24 },
      { date: "2024-05-10", amount: 0.24 },
      { date: "2024-02-09", amount: 0.24 },
    ],
  },
};
