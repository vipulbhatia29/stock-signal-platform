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
  in_db: boolean;
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

export interface DivestmentAlert {
  rule: "stop_loss" | "position_concentration" | "sector_concentration" | "weak_fundamentals";
  severity: "critical" | "warning";
  message: string;
  value: number;
  threshold: number;
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
  sector: string | null;
  alerts: DivestmentAlert[];
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

// ── Dividends ───────────────────────────────────────────────────────────────

export interface DividendPayment {
  ticker: string;
  ex_date: string;
  amount: number;
}

export interface DividendSummary {
  ticker: string;
  total_received: number;
  annual_dividends: number;
  dividend_yield: number | null;
  last_ex_date: string | null;
  payment_count: number;
  history: DividendPayment[];
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

  // Enriched fields (materialized during ingestion)
  revenue_growth: number | null;
  gross_margins: number | null;
  operating_margins: number | null;
  profit_margins: number | null;
  return_on_equity: number | null;
  market_cap: number | null;

  // Analyst targets
  analyst_target_mean: number | null;
  analyst_target_high: number | null;
  analyst_target_low: number | null;
  analyst_buy: number | null;
  analyst_hold: number | null;
  analyst_sell: number | null;
}

// ── User Preferences ─────────────────────────────────────────────────────────

export interface UserPreferences {
  default_stop_loss_pct: number;
  max_position_pct: number;
  max_sector_pct: number;
  min_cash_reserve_pct: number;
}

export interface UserPreferencesUpdate {
  default_stop_loss_pct?: number;
  max_position_pct?: number;
  max_sector_pct?: number;
  min_cash_reserve_pct?: number;
}

// ── Rebalancing ───────────────────────────────────────────────────────────────

export interface RebalancingSuggestion {
  ticker: string;
  action: "BUY_MORE" | "HOLD" | "AT_CAP";
  current_allocation_pct: number | null;
  target_allocation_pct: number;
  suggested_amount: number;
  reason: string;
}

export interface RebalancingResponse {
  total_value: number;
  available_cash: number;
  num_positions: number;
  suggestions: RebalancingSuggestion[];
}

// ── API Error ─────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export interface ChatSession {
  id: string;
  agent_type: "stock" | "general";
  title: string | null;
  is_active: boolean;
  created_at: string;
  last_active_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string | null;
  tool_calls: Record<string, unknown> | null;
  model_used: string | null;
  tokens_used: number | null;
  created_at: string;
}

export type StreamEventType =
  | "thinking"
  | "tool_start"
  | "tool_result"
  | "tool_error"
  | "token"
  | "done"
  | "error"
  | "provider_fallback"
  | "context_truncated"
  | "plan"
  | "evidence"
  | "decline";

export interface StreamEvent {
  type: StreamEventType;
  content?: string;
  tool?: string;
  params?: Record<string, unknown>;
  status?: string;
  data?: unknown;
  usage?: Record<string, unknown>;
  error?: string;
}

// Agent V2 event data types
export interface EvidenceItem {
  claim: string;
  source_tool: string;
  value?: string;
  timestamp?: string;
}

export interface FeedbackRequest {
  feedback: "up" | "down";
}

// ── Sectors ──────────────────────────────────────────────────────────────────

export type SectorScope = "portfolio" | "watchlist" | "all";

export interface SectorSummary {
  sector: string;
  stock_count: number;
  avg_composite_score: number | null;
  avg_return_pct: number | null;
  your_stock_count: number;
  allocation_pct: number | null;
}

export interface SectorSummaryResponse {
  sectors: SectorSummary[];
}

export interface SectorStock {
  ticker: string;
  name: string;
  composite_score: number | null;
  current_price: number | null;
  return_pct: number | null;
  is_held: boolean;
  is_watched: boolean;
}

export interface SectorStocksResponse {
  sector: string;
  stocks: SectorStock[];
}

export interface ExcludedTicker {
  ticker: string;
  reason: string;
}

export interface CorrelationData {
  sector: string;
  tickers: string[];
  matrix: number[][];
  period_days: number;
  excluded_tickers: ExcludedTicker[];
}

// ── Forecast Types ────────────────────────────────────────────

export interface ForecastHorizon {
  horizon_days: number;
  predicted_price: number;
  predicted_lower: number;
  predicted_upper: number;
  target_date: string;
  confidence_level: string;
  sharpe_direction: string;
}

export interface ForecastResponse {
  ticker: string;
  horizons: ForecastHorizon[];
  model_mape: number | null;
  model_status: string;
}

export interface PortfolioForecastHorizon {
  horizon_days: number;
  expected_return_pct: number;
  lower_pct: number;
  upper_pct: number;
  diversification_ratio: number;
  confidence_level: string;
}

export interface PortfolioForecastResponse {
  horizons: PortfolioForecastHorizon[];
  ticker_count: number;
  vix_regime: string;
}

export interface ScorecardHorizonBreakdown {
  horizon_days: number;
  total: number;
  correct: number;
  hit_rate: number;
  avg_alpha: number;
}

export interface ScorecardResponse {
  total_outcomes: number;
  overall_hit_rate: number;
  avg_alpha: number;
  buy_hit_rate: number;
  sell_hit_rate: number;
  worst_miss_pct: number;
  worst_miss_ticker: string;
  by_horizon: ScorecardHorizonBreakdown[];
}

// ── Alert Types ───────────────────────────────────────────────

export interface AlertResponse {
  id: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  ticker: string | null;
  is_read: boolean;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface UnreadAlertCount {
  unread_count: number;
}
