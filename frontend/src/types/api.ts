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

export interface TokenRefreshRequest {
  refresh_token: string;
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
  suggested_amount: number | null;
}

export interface PaginatedRecommendations {
  recommendations: Recommendation[];
  total: number;
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

export interface PaginatedTransactions {
  transactions: Transaction[];
  total: number;
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
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  feedback: string | null;
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

export interface ChatRequest {
  message: string;
  session_id?: string;
  agent_type?: "stock" | "general";
}

export interface AdminChatSessionSummary {
  id: string;
  agent_type: string;
  title: string | null;
  is_active: boolean;
  decline_count: number;
  user_email: string;
  message_count: number;
  created_at: string;
  last_active_at: string;
}

export interface AdminChatSessionListResponse {
  total: number;
  sessions: AdminChatSessionSummary[];
}

export interface AdminChatTranscriptResponse {
  session: AdminChatSessionSummary;
  messages: ChatMessage[];
}

export interface AdminChatStatsResponse {
  total_sessions: number;
  total_messages: number;
  active_sessions: number;
  feedback_up: number;
  feedback_down: number;
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
  severity: "critical" | "warning" | "info";
  title: string;
  message: string;
  ticker: string | null;
  is_read: boolean;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AlertListResponse {
  alerts: AlertResponse[];
  total: number;
  unread_count: number;
}

export interface BatchReadRequest {
  alert_ids: string[];
}

export interface BatchReadResponse {
  updated: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

// ── Intelligence ──────────────────────────────────────────────────────────────

export interface NewsItem {
  title: string;
  link: string;
  publisher: string | null;
  published: string | null;
  source: string;
}

export interface StockNewsResponse {
  ticker: string;
  articles: NewsItem[];
  fetched_at: string;
}

export interface UpgradeDowngrade {
  firm: string;
  to_grade: string;
  from_grade: string | null;
  action: string;
  date: string;
}

export interface InsiderTransaction {
  insider_name: string;
  relation: string | null;
  transaction_type: string;
  shares: number;
  value: number | null;
  date: string;
}

export interface ShortInterest {
  short_percent_of_float: number;
  short_ratio: number | null;
  shares_short: number | null;
}

export interface StockIntelligenceResponse {
  ticker: string;
  upgrades_downgrades: UpgradeDowngrade[];
  insider_transactions: InsiderTransaction[];
  next_earnings_date: string | null;
  eps_revisions: Record<string, unknown> | null;
  short_interest: ShortInterest | null;
  fetched_at: string;
}

// ── Portfolio Health ──────────────────────────────────────────────────────────

export interface HealthComponent {
  name: string;
  score: number;
  weight: number;
  detail: string;
}

export interface PositionHealth {
  ticker: string;
  weight_pct: number;
  signal_score: number | null;
  sector: string | null;
  contribution: "strength" | "drag";
}

export interface PortfolioHealthResult {
  health_score: number;
  grade: string;
  components: HealthComponent[];
  metrics: Record<string, unknown>;
  top_concerns: string[];
  top_strengths: string[];
  position_details: PositionHealth[];
}

export interface PortfolioHealthSnapshotResponse {
  snapshot_date: string;
  health_score: number;
  grade: string;
  diversification_score: number;
  signal_quality_score: number;
  risk_score: number;
  income_score: number;
  sector_balance_score: number;
  hhi: number;
  weighted_beta: number | null;
  weighted_sharpe: number | null;
  weighted_yield: number | null;
  position_count: number;
}

// ── Market ────────────────────────────────────────────────────────────────────

export interface IndexPerformance {
  name: string;
  ticker: string;
  price: number;
  change_pct: number;
}

export interface SectorPerformance {
  sector: string;
  etf: string;
  change_pct: number;
}

export interface MarketBriefingResult {
  indexes: IndexPerformance[];
  sector_performance: SectorPerformance[];
  portfolio_news: Record<string, unknown>[];
  upcoming_earnings: Record<string, unknown>[];
  top_movers: Record<string, unknown>;
  briefing_date: string;
}

// ── Health ─────────────────────────────────────────────────────────────────────

export interface MCPToolsStatus {
  enabled: boolean;
  mode: "stdio" | "fallback_direct" | "direct" | "disabled";
  healthy: boolean;
  tool_count: number;
  restarts: number;
  uptime_seconds: number | null;
  last_error: string | null;
  fallback_since: string | null;
}

export interface DependencyStatus {
  healthy: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  redis: DependencyStatus;
  database: DependencyStatus;
  mcp_tools: MCPToolsStatus;
}

// ── LLM Config ────────────────────────────────────────────────────────────────

export interface LLMModelConfigResponse {
  id: number;
  provider: string;
  model_name: string;
  tier: string;
  priority: number;
  is_enabled: boolean;
  tpm_limit: number | null;
  rpm_limit: number | null;
  tpd_limit: number | null;
  rpd_limit: number | null;
  cost_per_1k_input: number;
  cost_per_1k_output: number;
  notes: string | null;
}

export interface LLMModelConfigUpdate {
  priority?: number;
  is_enabled?: boolean;
  tpm_limit?: number | null;
  rpm_limit?: number | null;
  tpd_limit?: number | null;
  rpd_limit?: number | null;
  cost_per_1k_input?: number;
  cost_per_1k_output?: number;
  notes?: string | null;
}

export interface TierToggleRequest {
  model: string;
  enabled: boolean;
}

// ── Observability ─────────────────────────────────────────────────────────────

export interface KPIResponse {
  queries_today: number;
  avg_latency_ms: number;
  avg_cost_per_query: number;
  pass_rate: number | null;
  fallback_rate_pct: number;
}

export interface QueryRow {
  query_id: string;
  timestamp: string;
  query_text: string;
  agent_type: string;
  tools_used: string[];
  llm_calls: number;
  llm_models: string[];
  db_calls: number;
  external_calls: number;
  external_sources: string[];
  total_cost_usd: number;
  duration_ms: number;
  score: number | null;
  status: string;
}

export interface QueryListResponse {
  items: QueryRow[];
  total: number;
  page: number;
  size: number;
}

export interface StepDetail {
  step_number: number;
  action: string;
  type_tag: string;
  model_name: string | null;
  input_summary: string | null;
  output_summary: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  cache_hit: boolean;
}

export interface QueryDetailResponse {
  query_id: string;
  query_text: string;
  steps: StepDetail[];
  langfuse_trace_url: string | null;
}

export interface LangfuseURLResponse {
  url: string | null;
}

export interface AssessmentRunSummary {
  id: string;
  trigger: string;
  total_queries: number;
  passed_queries: number;
  pass_rate: number;
  total_cost_usd: number;
  started_at: string;
  completed_at: string;
}

export interface AssessmentHistoryResponse {
  items: AssessmentRunSummary[];
}

// ── Recommendations (extended) ────────────────────────────────────────────────

export interface StockCandidate {
  ticker: string;
  name: string;
  sector: string | null;
  recommendation_score: number;
  sources: string[];
  rationale: string[];
  signal_score: number | null;
  forward_pe: number | null;
  dividend_yield: number | null;
}

export interface RecommendationResult {
  candidates: StockCandidate[];
  portfolio_context: Record<string, unknown>;
}

// ── Stock (extended) ──────────────────────────────────────────────────────────

export interface OHLCResponse {
  ticker: string;
  period: string;
  count: number;
  timestamps: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
}

// ── Benchmark ────��────────────────────────────────────────────────────────────

export interface BenchmarkSeries {
  ticker: string;
  name: string;
  dates: string[];
  pct_change: number[];
}

export interface BenchmarkComparisonResponse {
  ticker: string;
  period: string;
  series: BenchmarkSeries[];
}
