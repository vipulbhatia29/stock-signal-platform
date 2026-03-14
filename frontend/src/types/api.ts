// TypeScript types mirroring backend Pydantic schemas.
// Keep in sync with backend/schemas/*.py

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface UserRegisterRequest {
  email: string;
  password: string;
}

export interface UserRegisterResponse {
  id: string;
  email: string;
  created_at: string;
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── Stock ─────────────────────────────────────────────────────────────────────

export interface StockResponse {
  id: string;
  ticker: string;
  name: string;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  is_active: boolean;
}

export interface StockSearchResponse {
  ticker: string;
  name: string;
  exchange: string | null;
  sector: string | null;
}

// ── Price ─────────────────────────────────────────────────────────────────────

export interface PricePoint {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type PricePeriod =
  | "1mo"
  | "3mo"
  | "6mo"
  | "1y"
  | "2y"
  | "5y"
  | "10y";

// ── Signals ───────────────────────────────────────────────────────────────────

export interface RSISignal {
  value: number | null;
  signal: string | null;
}

export interface MACDSignal {
  value: number | null;
  histogram: number | null;
  signal: string | null;
}

export interface SMASignal {
  sma_50: number | null;
  sma_200: number | null;
  signal: string | null;
}

export interface BollingerSignal {
  upper: number | null;
  lower: number | null;
  position: string | null;
}

export interface ReturnsMetrics {
  annual_return: number | null;
  volatility: number | null;
  sharpe: number | null;
}

export interface SignalResponse {
  ticker: string;
  computed_at: string | null;
  rsi: RSISignal;
  macd: MACDSignal;
  sma: SMASignal;
  bollinger: BollingerSignal;
  returns: ReturnsMetrics;
  composite_score: number | null;
  is_stale: boolean;
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export interface WatchlistAddRequest {
  ticker: string;
}

export interface WatchlistItem {
  id: string;
  ticker: string;
  name: string | null;
  sector: string | null;
  composite_score: number | null;
  added_at: string;
  current_price: number | null;
  price_updated_at: string | null;
  price_acknowledged_at: string | null;
}

// ── Recommendations ───────────────────────────────────────────────────────────

export interface Recommendation {
  ticker: string;
  action: string;
  confidence: string;
  composite_score: number;
  price_at_recommendation: number;
  reasoning: Record<string, unknown> | null;
  generated_at: string;
  is_actionable: boolean;
}

// ── Ingestion ─────────────────────────────────────────────────────────────────

export interface IngestResponse {
  ticker: string;
  name: string;
  rows_fetched: number;
  composite_score: number | null;
  status: string;
}

// ── Bulk Signals (Screener) ───────────────────────────────────────────────────

export interface BulkSignalItem {
  ticker: string;
  name: string;
  sector: string | null;
  composite_score: number | null;
  rsi_value: number | null;
  rsi_signal: string | null;
  macd_signal: string | null;
  sma_signal: string | null;
  bb_position: string | null;
  annual_return: number | null;
  volatility: number | null;
  sharpe_ratio: number | null;
  computed_at: string | null;
  is_stale: boolean;
  price_history: number[] | null;
}

export interface BulkSignalsResponse {
  total: number;
  items: BulkSignalItem[];
}

// ── Signal History ────────────────────────────────────────────────────────────

export interface SignalHistoryItem {
  computed_at: string;
  composite_score: number | null;
  rsi_value: number | null;
  rsi_signal: string | null;
  macd_value: number | null;
  macd_signal: string | null;
  sma_signal: string | null;
  bb_position: string | null;
}

// ── Indexes ───────────────────────────────────────────────────────────────────

export interface IndexResponse {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  stock_count: number;
}

export interface IndexStockItem {
  ticker: string;
  name: string;
  sector: string | null;
  exchange: string | null;
  latest_price: number | null;
  composite_score: number | null;
  rsi_signal: string | null;
  macd_signal: string | null;
}

export interface IndexStocksResponse {
  index_name: string;
  total: number;
  items: IndexStockItem[];
}

// ── Task / Refresh ────────────────────────────────────────────────────────────

export interface TaskStatus {
  task_id: string;
  state: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE";
}

export interface RefreshTask {
  ticker: string;
  task_id: string;
}

// ── Portfolio ─────────────────────────────────────────────────────────────────

export interface Transaction {
  id: string;
  portfolio_id: string;
  ticker: string;
  transaction_type: "BUY" | "SELL";
  shares: number;
  price_per_share: number;
  transacted_at: string;
  notes: string | null;
  created_at: string;
}

export interface TransactionCreate {
  ticker: string;
  transaction_type: "BUY" | "SELL";
  shares: string;
  price_per_share: string;
  transacted_at: string;
  notes?: string;
}

export interface Position {
  ticker: string;
  shares: number;
  avg_cost_basis: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  allocation_pct: number | null;
}

export interface SectorAllocation {
  sector: string;
  market_value: number;
  pct: number;
  over_limit: boolean;
}

export interface PortfolioSummary {
  total_value: number;
  total_cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  position_count: number;
  sectors: SectorAllocation[];
}

export interface PortfolioSnapshot {
  snapshot_date: string;
  total_value: number;
  total_cost_basis: number;
  unrealized_pnl: number;
  position_count: number;
}

// ── Fundamentals ─────────────────────────────────────────────────────────────

export interface PiotroskiBreakdown {
  positive_roa: number | null;
  positive_cfo: number | null;
  improving_roa: number | null;
  accruals: number | null;
  decreasing_leverage: number | null;
  improving_liquidity: number | null;
  no_dilution: number | null;
  improving_gross_margin: number | null;
  improving_asset_turnover: number | null;
}

export interface FundamentalsResponse {
  ticker: string;
  pe_ratio: number | null;
  peg_ratio: number | null;
  fcf_yield: number | null;
  debt_to_equity: number | null;
  piotroski_score: number | null;
  piotroski_breakdown: PiotroskiBreakdown;
}

// ── API Error ─────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
}
