/**
 * Default MSW handlers — happy-path responses for all major API endpoints.
 *
 * These are the baseline handlers used in every test. Individual tests can
 * override them by calling server.use() with a one-time handler.
 */

import { http, HttpResponse } from "msw";

// ── Auth ─────────────────────────────────────────────────────────────────────

export const authHandlers = [
  http.get("/api/v1/auth/me", () => {
    return HttpResponse.json({
      id: "user-1",
      email: "test@example.com",
      role: "user",
      email_verified: true,
      has_password: true,
      created_at: "2025-01-01T00:00:00Z",
    });
  }),

  http.post("/api/v1/auth/login", async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    if (body.email === "test@example.com" && body.password === "TestPass1") {
      return HttpResponse.json({ message: "Login successful" }, { status: 200 });
    }
    return HttpResponse.json({ detail: "Invalid credentials" }, { status: 401 });
  }),

  http.post("/api/v1/auth/register", async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    return HttpResponse.json(
      { id: "user-new", email: body.email },
      { status: 201 }
    );
  }),

  http.post("/api/v1/auth/refresh", () => {
    return HttpResponse.json({ message: "Token refreshed" }, { status: 200 });
  }),
];

// ── Market / Stocks ───────────────────────────────────────────────────────────

export const marketHandlers = [
  http.get("/api/v1/market/briefing", () => {
    return HttpResponse.json({
      indexes: [
        { ticker: "SPY", name: "S&P 500", price: 520.45, change_pct: 0.42 },
        { ticker: "QQQ", name: "NASDAQ", price: 440.12, change_pct: 0.67 },
        { ticker: "DIA", name: "Dow Jones", price: 392.34, change_pct: 0.18 },
      ],
      sector_performance: [],
      portfolio_news: [],
      upcoming_earnings: [],
      top_movers: {
        gainers: [
          { ticker: "NVDA", current_price: 875.0, change_pct: 3.21, macd_signal_label: "bullish_crossover", composite_score: 8.5 },
          { ticker: "MSFT", current_price: 415.2, change_pct: 1.45, macd_signal_label: "bullish", composite_score: 9.1 },
        ],
        losers: [
          { ticker: "INTC", current_price: 32.1, change_pct: -2.34, macd_signal_label: "bearish", composite_score: 3.2 },
          { ticker: "BA", current_price: 195.6, change_pct: -1.89, macd_signal_label: null, composite_score: 4.1 },
        ],
      },
      briefing_date: "2026-04-02",
    });
  }),

  http.get("/api/v1/stocks/recommendations", () => {
    return HttpResponse.json({
      recommendations: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          action: "BUY",
          composite_score: 8.7,
          sector: "Technology",
        },
        {
          ticker: "MSFT",
          name: "Microsoft Corp.",
          action: "BUY",
          composite_score: 9.1,
          sector: "Technology",
        },
        {
          ticker: "NVDA",
          name: "NVIDIA Corp.",
          action: "WATCH",
          composite_score: 7.3,
          sector: "Technology",
        },
      ],
      total: 3,
    });
  }),

  http.get("/api/v1/stocks/signals/bulk", () => {
    return HttpResponse.json({
      items: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          rsi_value: 42.5,
          rsi_signal: "neutral",
          macd_signal: "bullish_crossover",
          sma_signal: "above",
          composite_score: 8.7,
          sharpe_ratio: 1.45,
        },
        {
          ticker: "MSFT",
          name: "Microsoft Corp.",
          rsi_value: 55.3,
          rsi_signal: "neutral",
          macd_signal: "bullish",
          sma_signal: "above",
          composite_score: 9.1,
          sharpe_ratio: 1.72,
        },
      ],
      total: 2,
      page: 1,
    });
  }),

  http.get("/api/v1/stocks/watchlist", () => {
    return HttpResponse.json([
      { ticker: "AAPL", name: "Apple Inc.", sector: "Technology" },
      { ticker: "MSFT", name: "Microsoft Corp.", sector: "Technology" },
    ]);
  }),

  http.get("/api/v1/stocks/:ticker/signals", ({ params }) => {
    const { ticker } = params as { ticker: string };
    return HttpResponse.json({
      ticker,
      computed_at: "2026-04-02T10:00:00Z",
      rsi: { value: 42.5, signal: "neutral" },
      macd: { value: 0.45, histogram: 0.12, signal: "bullish_crossover" },
      sma: { sma_50: 185.3, sma_200: 172.1, signal: "above" },
      bollinger: { upper: 195.0, lower: 175.0, position: "middle" },
      returns: { annual_return: 0.18, volatility: 0.22, sharpe: 1.45 },
      composite_score: 8.7,
      is_stale: false,
    });
  }),

  http.get("/api/v1/stocks/:ticker/news", () => {
    return HttpResponse.json({
      articles: [],
      ticker_count: 0,
    });
  }),

  http.get("/api/v1/stocks/:ticker/intelligence", () => {
    return HttpResponse.json({
      summary: "Bullish outlook for this stock.",
      key_points: [],
      generated_at: "2026-04-02T10:00:00Z",
    });
  }),

  http.get("/api/v1/stocks/:ticker/benchmark", () => {
    return HttpResponse.json([]);
  }),

  http.get("/api/v1/stocks/:ticker/ohlc", () => {
    return HttpResponse.json({ candles: [] });
  }),

  http.get("/api/v1/stocks/:ticker/analytics", () => {
    return HttpResponse.json({
      ticker: "AAPL",
      sortino: 1.8,
      max_drawdown: -0.12,
      alpha: 0.02,
      beta: 1.12,
      data_days: 365,
    });
  }),

  http.get("/api/v1/stocks/:ticker/signal-history", () => {
    return HttpResponse.json([]);
  }),

  http.get("/api/v1/portfolio/dividends/:ticker", () => {
    return HttpResponse.json({
      ticker: "AAPL",
      annual_yield: 0.0052,
      dividends: [],
    });
  }),

  http.get("/api/v1/stocks/:ticker/prices", ({ params }) => {
    const { ticker } = params as { ticker: string };
    const basePrice = ticker === "AAPL" ? 185 : 415;
    const now = new Date("2026-04-02");
    const prices = Array.from({ length: 30 }, (_, i) => {
      const date = new Date(now);
      date.setDate(date.getDate() - (30 - i));
      const close = basePrice + (Math.random() - 0.5) * 10;
      return {
        date: date.toISOString().split("T")[0],
        open: close - 1,
        high: close + 2,
        low: close - 2,
        close,
        volume: 50000000 + Math.floor(Math.random() * 10000000),
      };
    });
    return HttpResponse.json(prices);
  }),

  http.get("/api/v1/stocks/:ticker/fundamentals", ({ params }) => {
    const { ticker } = params as { ticker: string };
    return HttpResponse.json({
      ticker,
      pe_ratio: 28.5,
      market_cap: 2850000000000,
      beta: 1.12,
      dividend_yield: 0.0052,
      eps: 6.53,
      revenue_ttm: 394000000000,
      profit_margin: 0.253,
      debt_to_equity: 1.45,
    });
  }),
];

// ── Portfolio ─────────────────────────────────────────────────────────────────

export const portfolioHandlers = [
  http.get("/api/v1/portfolio/summary", () => {
    return HttpResponse.json({
      portfolio_id: "portfolio-1",
      total_value: 52340.0,
      total_cost_basis: 45000.0,
      unrealized_pnl: 7340.0,
      unrealized_pnl_pct: 16.31,
      position_count: 5,
      sectors: [
        { sector: "Technology", value: 30000, weight: 0.573 },
        { sector: "Healthcare", value: 12340, weight: 0.236 },
        { sector: "Finance", value: 10000, weight: 0.191 },
      ],
    });
  }),

  http.get("/api/v1/portfolio/positions", () => {
    return HttpResponse.json([
      {
        ticker: "AAPL",
        shares: 50,
        avg_cost_basis: 165.0,
        current_price: 185.25,
        market_value: 9262.5,
        unrealized_pnl: 1012.5,
        unrealized_pnl_pct: 12.27,
        allocation_pct: 17.7,
        sector: "Technology",
        alerts: [],
      },
      {
        ticker: "MSFT",
        shares: 20,
        avg_cost_basis: 380.0,
        current_price: 415.5,
        market_value: 8310.0,
        unrealized_pnl: 710.0,
        unrealized_pnl_pct: 9.34,
        allocation_pct: 15.9,
        sector: "Technology",
        alerts: [],
      },
      {
        ticker: "JNJ",
        shares: 30,
        avg_cost_basis: 155.0,
        current_price: 160.2,
        market_value: 4806.0,
        unrealized_pnl: 156.0,
        unrealized_pnl_pct: 3.35,
        allocation_pct: 9.2,
        sector: "Healthcare",
        alerts: [],
      },
    ]);
  }),

  http.get("/api/v1/portfolio/rebalancing", () => {
    return HttpResponse.json({
      suggestions: [],
      total_value: 52340.0,
      target_allocations: [],
    });
  }),

  http.get("/api/v1/portfolio/history", () => {
    const now = new Date("2026-04-02");
    const history = Array.from({ length: 30 }, (_, i) => {
      const date = new Date(now);
      date.setDate(date.getDate() - (30 - i));
      return {
        date: date.toISOString().split("T")[0],
        value: 45000 + i * 250 + (Math.random() - 0.3) * 500,
      };
    });
    return HttpResponse.json(history);
  }),

  http.get("/api/v1/portfolio/health", () => {
    return HttpResponse.json({
      health_score: 78,
      grade: "B+",
      components: [],
      metrics: {},
      top_concerns: ["Concentration in Technology"],
      top_strengths: ["Positive momentum"],
      position_details: [],
    });
  }),

  http.get("/api/v1/portfolio/analytics", () => {
    return HttpResponse.json({
      sharpe_ratio: 1.45,
      sortino_ratio: 1.82,
      max_drawdown: -0.12,
      calmar_ratio: 1.36,
      volatility: 0.18,
      benchmark_correlation: 0.82,
    });
  }),

  http.get("/api/v1/portfolio/transactions", () => {
    return HttpResponse.json({
      transactions: [
        {
          id: "txn-1",
          ticker: "AAPL",
          transaction_type: "BUY",
          shares: 50,
          price_per_share: 165.0,
          transacted_at: "2025-06-15T10:00:00Z",
          notes: "Initial position",
        },
        {
          id: "txn-2",
          ticker: "MSFT",
          transaction_type: "BUY",
          shares: 20,
          price_per_share: 380.0,
          transacted_at: "2025-07-01T10:00:00Z",
          notes: null,
        },
      ],
      total: 2,
      page: 1,
      per_page: 50,
    });
  }),

  http.post("/api/v1/portfolio/transactions", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      {
        id: "txn-new",
        ...body,
        transacted_at: "2026-04-02T10:00:00Z",
      },
      { status: 201 }
    );
  }),
];

// ── Alerts ────────────────────────────────────────────────────────────────────

export const alertHandlers = [
  http.get("/api/v1/alerts", () => {
    return HttpResponse.json({
      alerts: [
        {
          id: "alert-1",
          ticker: "AAPL",
          alert_type: "signal",
          title: "BUY Signal",
          message: "AAPL composite score reached 8.7",
          severity: "info",
          is_read: false,
          created_at: "2026-04-02T09:00:00Z",
          metadata: {},
        },
        {
          id: "alert-2",
          ticker: "INTC",
          alert_type: "price",
          title: "Price Drop",
          message: "INTC dropped 2.34% today",
          severity: "warning",
          is_read: true,
          created_at: "2026-04-01T15:30:00Z",
          metadata: {},
        },
      ],
      total: 2,
      unread_count: 1,
    });
  }),
];

// ── News ──────────────────────────────────────────────────────────────────────

export const newsHandlers = [
  http.get("/api/v1/news/dashboard", () => {
    return HttpResponse.json({
      articles: [
        {
          title: "Apple announces new AI features",
          link: "https://example.com/apple-ai",
          publisher: "Reuters",
          published: "2h ago",
          source: "news",
          portfolio_ticker: "AAPL",
        },
        {
          title: "Microsoft cloud revenue beats estimates",
          link: "https://example.com/msft-cloud",
          publisher: "Bloomberg",
          published: "3h ago",
          source: "news",
          portfolio_ticker: "MSFT",
        },
      ],
      ticker_count: 2,
    });
  }),
];

// ── Portfolio Forecast (BL + MC + CVaR) ─────────────────────────────────────

export const forecastHandlers = [
  http.get("/api/v1/portfolio/:id/forecast", () => {
    return HttpResponse.json({
      portfolio_id: "portfolio-1",
      forecast_date: "2026-04-03",
      horizon_days: 90,
      bl: {
        portfolio_expected_return: 0.125,
        risk_free_rate: 0.05,
        per_ticker: [
          { ticker: "AAPL", expected_return: 0.18, view_confidence: 0.8 },
          { ticker: "MSFT", expected_return: 0.15, view_confidence: 0.7 },
          { ticker: "GOOGL", expected_return: 0.12, view_confidence: 0.6 },
        ],
      },
      monte_carlo: {
        simulation_days: 90,
        initial_value: 100000,
        terminal_median: 103200,
        terminal_p5: 88500,
        terminal_p95: 118900,
        bands: {
          p5: [100000, 97000, 94000, 88500],
          p25: [100000, 99000, 98000, 96500],
          p50: [100000, 101000, 102000, 103200],
          p75: [100000, 103000, 106000, 110000],
          p95: [100000, 106000, 112000, 118900],
        },
      },
      cvar: {
        cvar_95_pct: -12.5,
        cvar_99_pct: -18.3,
        var_95_pct: -8.2,
        var_99_pct: -14.1,
        description_95: "In a bad month (1-in-20): -12.5%",
        description_99: "In a very bad month (1-in-100): -18.3%",
      },
    });
  }),
];

// ── Convergence ─────────────────────────────────────────────────────────────

export const convergenceHandlers = [
  http.get("/api/v1/convergence/:ticker", ({ params }) => {
    const ticker = (params.ticker as string).toUpperCase();
    return HttpResponse.json({
      ticker,
      date: "2026-04-03",
      signals: [
        { signal: "rsi", direction: "bullish", value: 35.0 },
        { signal: "macd", direction: "bullish", value: 0.05 },
        { signal: "sma", direction: "bullish", value: 200.0 },
        { signal: "piotroski", direction: "bullish", value: 7 },
        { signal: "forecast", direction: "bearish", value: -0.04 },
        { signal: "news", direction: "neutral", value: 0.1 },
      ],
      signals_aligned: 4,
      convergence_label: "weak_bull",
      composite_score: 7.8,
      divergence: {
        is_divergent: true,
        forecast_direction: "bearish",
        technical_majority: "bullish",
        historical_hit_rate: 0.61,
        sample_count: 23,
      },
      rationale:
        "4 of 6 signals are bullish. However, 90-day forecast is bearish (Forecast predicts -4.0%). When the forecast disagreed with technicals like this, the forecast was right 61% of the time (23 cases).",
    });
  }),

  http.get("/api/v1/convergence/portfolio/:id", () => {
    return HttpResponse.json({
      portfolio_id: "portfolio-1",
      date: "2026-04-03",
      positions: [
        {
          ticker: "AAPL",
          weight: 0.6,
          convergence_label: "strong_bull",
          signals_aligned: 5,
          divergence: { is_divergent: false, forecast_direction: null, technical_majority: null, historical_hit_rate: null, sample_count: null },
        },
        {
          ticker: "MSFT",
          weight: 0.4,
          convergence_label: "weak_bear",
          signals_aligned: 3,
          divergence: { is_divergent: true, forecast_direction: "bearish", technical_majority: "bullish", historical_hit_rate: 0.55, sample_count: 12 },
        },
      ],
      bullish_pct: 0.6,
      bearish_pct: 0.4,
      mixed_pct: 0.0,
      divergent_positions: ["MSFT"],
    });
  }),
];

// ── All handlers ──────────────────────────────────────────────────────────────

export const handlers = [
  ...authHandlers,
  ...marketHandlers,
  ...portfolioHandlers,
  ...alertHandlers,
  ...newsHandlers,
  ...forecastHandlers,
  ...convergenceHandlers,
];
