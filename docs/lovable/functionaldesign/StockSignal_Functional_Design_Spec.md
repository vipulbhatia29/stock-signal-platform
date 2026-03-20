# Stock Signal Platform — Functional Design Specification

> **Version**: 1.0  
> **Date**: 2026-03-19  
> **Stack**: React 18 · TypeScript · Vite · Tailwind CSS · Framer Motion · Recharts · React Router v6  
> **Preview**: https://id-preview--00bdab20-3148-4613-85ee-a4b61752b43c.lovable.app

---

## Table of Contents

1. [Application Architecture](#1-application-architecture)
2. [Design System & Theming](#2-design-system--theming)
3. [Shell Layout](#3-shell-layout)
4. [Authentication Pages](#4-authentication-pages)
5. [Dashboard Page](#5-dashboard-page)
6. [Screener Page](#6-screener-page)
7. [Stock Detail Page](#7-stock-detail-page)
8. [Portfolio Page](#8-portfolio-page)
9. [Sectors Page](#9-sectors-page)
10. [AI Chat Panel](#10-ai-chat-panel)
11. [Shared Components](#11-shared-components)
12. [State Management & Contexts](#12-state-management--contexts)
13. [Data Model & Types](#13-data-model--types)
14. [Mock Data Layer](#14-mock-data-layer)
15. [Routing](#15-routing)

---

## 1. Application Architecture

### File Structure
```
src/
├── assets/             # Logo (logo.png — cyan S-arrow icon, transparent)
├── components/
│   ├── shared/         # 7 reusable data-display components
│   ├── shell/          # App shell: layout, sidebar, topbar, chat panel
│   └── ui/             # shadcn/ui primitives (50+ components)
├── contexts/           # ChatContext, StockRefreshContext
├── hooks/              # use-mobile, use-toast
├── lib/                # mock-data.ts, utils.ts
├── pages/              # Auth, Dashboard, Screener, StockDetail, Portfolio, Sectors, NotFound
└── index.css           # Design tokens (CSS custom properties)
```

### Key Patterns
- **All data is mock/simulated** — no backend calls. Prices, signals, scores are generated client-side.
- **Stock refresh simulation** — `StockRefreshContext` provides live-feeling data updates with per-ticker refresh and stale detection.
- **Responsive layout** — All grids adapt when the chat panel is open (`isNarrow` flag derived from `chatOpen`).
- **Framer Motion** — Every card, row, and section entrance is animated with staggered `initial/animate` transitions.

---

## 2. Design System & Theming

### Color Palette (HSL in CSS custom properties)

| Token | HSL | Purpose |
|-------|-----|---------|
| `--background` | `228 43% 7%` | Page background (#0a0e1a) |
| `--foreground` | `215 25% 90%` | Primary text |
| `--card` | `220 26% 11%` | Card backgrounds (#111827) |
| `--card2` | `226 30% 16%` | Elevated cards, inputs (#1a2035) |
| `--primary` | `187 82% 54%` | Cyan accent (#22d3ee) |
| `--gain` | `142 71% 45%` | Green — positive values (#22c55e) |
| `--loss` | `0 84% 60%` | Red — negative values (#ef4444) |
| `--warning` | `38 92% 50%` | Amber — caution states (#f59e0b) |
| `--muted` | `220 17% 20%` | Muted backgrounds |
| `--muted-foreground` | `215 16% 47%` | Secondary text (#64748b) |
| `--border` | `217 25% 17%` | Borders (#1e293b) |
| `--subtle` | `215 14% 34%` | Subtle elements (#475569) |

### Typography
- **Display/UI**: `Sora` (var `--font-sora`)
- **Monospace/Data**: `JetBrains Mono` (var `--font-mono`)
- Text sizes: Heavy use of `text-[10px]`, `text-xs`, `text-sm` — data-dense terminal aesthetic

### Interactions
- **Hover states**: `hover:bg-hov` (custom utility), `hover:border-primary/30`
- **Active indicator on sidebar**: Left cyan bar `w-0.5 bg-primary`
- **Glow effects on CTAs**: `shadow-[0_0_20px_hsl(var(--primary)/0.25)]`

### Dark-only Mode
The app is dark-mode only. No light theme. All colors assume a dark background.

---

## 3. Shell Layout

**File**: `src/components/shell/ShellLayout.tsx`

```
┌──────────────────────────────────────────────┐
│ [Sidebar 54px] │  Topbar (h-12)              │ [ChatPanel 360px] │
│                │──────────────────────────────│                   │
│  Logo          │                              │  AI Analyst       │
│  Dashboard     │  <Outlet /> (page content)   │  Chat messages    │
│  Screener      │                              │  Input            │
│  Portfolio     │                              │                   │
│  Sectors       │                              │                   │
│  ─────         │                              │                   │
│  Settings ⊘    │                              │                   │
│  Logout        │                              │                   │
└──────────────────────────────────────────────┘
```

### SidebarNav (`src/components/shell/SidebarNav.tsx`)
- **Width**: Fixed 54px icon-only sidebar
- **Logo**: `src/assets/logo.png` with cyan glow drop-shadow
- **Navigation items** (icon + tooltip on hover):
  - Dashboard (`/`) — LayoutDashboard icon
  - Screener (`/screener`) — Search icon
  - Portfolio (`/portfolio`) — Briefcase icon
  - Sectors (`/sectors`) — PieChart icon
- **Active state**: Cyan highlight background + left bar indicator
- **Bottom section**:
  - Settings button (disabled, "Coming Soon" tooltip)
  - Logout button → navigates to `/login`, hover turns red (`destructive`)
- Uses `react-router-dom` `NavLink` for routing, `useLocation` for active detection

### Topbar (`src/components/shell/Topbar.tsx`)
- **Breadcrumb**: "StockSignal / {PageName}" — dynamic based on current route. For `/stocks/:ticker` shows the ticker uppercased.
- **Search bar** (center, `md:` breakpoint): Text input "Search stocks to add..." with `/` keyboard hint badge + Refresh All button (RefreshCw icon, spins when `refreshingAll`)
- **Right section**:
  - Market status indicator — green pulsing dot if NYSE open (M-F 9:30-16:00 ET), gray otherwise
  - Signal count button — "5 signals" with Activity icon
  - Bell notification button
  - AI Analyst toggle — Opens/closes chat panel. Styled differently when active (cyan bg + border)

---

## 4. Authentication Pages

**File**: `src/pages/Auth.tsx`  
**Routes**: `/login`, `/register`

### Layout
Split-panel design:
- **Left panel** (hidden on mobile, `lg:` breakpoint): Brand showcase with logo, feature bullets, animated sparkline SVG, glowing orb background effects
- **Right panel**: Auth form

### Login Page (`/login`)
- Mobile logo fallback (shown `lg:hidden`)
- "Welcome back" heading
- **Google OAuth button**: "Continue with Google" with official colored G icon — full width, top of form
- "OR" divider
- Email input (Mail icon)
- Password input (Lock icon)
- "Remember me" checkbox + "Forgot password?" link
- **Sign in button**: Cyan primary with glow shadow and ArrowRight icon
- "Don't have an account? Create one" → links to `/register`

### Register Page (`/register`)
- Same split layout
- "Create account" heading, "Start your trading edge today"
- Google OAuth button
- "OR" divider
- Full name input (User icon)
- Email input (Mail icon)
- Password input (Lock icon)
- **Create account button**: Same cyan glow style
- "Already have an account? Sign in" → links to `/login`

### Shared Components
- `AuthInput`: Icon + label + styled input with focus ring animation (`focus-within:border-primary/50 focus-within:shadow`)
- `BrandPanel`: Left marketing panel with features (Real-time Signals, Deep Analytics, Portfolio Guard)
- `GoogleButton`: Full-width Google OAuth button with official SVG logo
- `OrDivider`: Horizontal rule with "OR" text

**Note**: Auth is UI-only (no backend). The consumer handles actual auth logic.

---

## 5. Dashboard Page

**File**: `src/pages/Dashboard.tsx`  
**Route**: `/`

### KPI Stat Tiles (5 tiles in a responsive grid)
Each tile has a colored gradient top border (2px accent line).

| Tile | Value | Sub-value | Accent |
|------|-------|-----------|--------|
| Portfolio Value | $3,370.15 | ↑ $524.30 | cyan |
| Unrealized P&L | -$2,984.85 | -46.97% | loss (red) |
| Signals | 5 Buy | 0 Hold · 0 Sell | gain (green) |
| Top Signal | GOOGL | Score 4.1 | cyan |
| Allocation | Donut chart | Click to explore sectors → | warning |

The Allocation tile renders an `AllocationDonut` mini chart. Clicking links to `/sectors`.

### Market Indexes (3 cards in a row)
Each `IndexCard` shows:
- Index name (S&P 500, NASDAQ-100, Dow 30)
- Current value (e.g., 5,321.40) with `ChangeIndicator`
- Stock count
- Mini `Sparkline` chart (right side)
- Chevron right on hover

### Action Required (2/3 width + 1/3 allocation)
**Left**: List of `RecommendationRow` items — 5 actionable signals:
- Icon badge (colored by action type: BUY=green↑, WATCH=cyan👁, AVOID=red↓, HOLD=amber—, SELL=red↓)
- Ticker (mono font, bold) + "Held" badge if in portfolio
- Action badge (BUY/WATCH/AVOID) + confidence level (HIGH/MEDIUM/LOW)
- Reasoning text (truncated)
- `RefreshIndicator` + composite score
- Entire row links to `/stocks/:ticker`

**Right**: Large `AllocationDonut` with sector breakdown. Links to `/sectors`.

### Watchlist (grid of stock cards)
4 columns (3 when chat open). Each card:
- Ticker + "Held" badge + `ScoreBadge`
- Company name (truncated)
- `Sparkline` chart (top right)
- Price + `ChangeIndicator`
- `ScoreBar` (10-segment bar)
- `SignalBadge` (BUY/WATCH/AVOID) + `RefreshIndicator`
- Clicking any card navigates to `/stocks/:ticker`

---

## 6. Screener Page

**File**: `src/pages/Screener.tsx`  
**Route**: `/screener`

### Filter Bar
- **RSI filter**: Dropdown — All, OVERSOLD, NEUTRAL, OVERBOUGHT
- **MACD filter**: Dropdown — All, BULLISH, BEARISH
- **Sector filter**: Dropdown — All + dynamically derived sector names
- **Reset button**: Appears when any filter is active (RotateCcw icon)
- **Density toggle**: Comfortable / Compact (table view only)
- **View mode toggle**: Table (List icon) / Grid (LayoutGrid icon)

### Table View (3 tab variants)

**Overview tab**: Ticker (linked, with "Held" badge), Name, Sector, Price, Change, Score (ScoreBar + ScoreBadge)

**Signals tab**: Ticker, RSI (value + SignalBadge), MACD (value + SignalBadge), SMA (SignalBadge), Bollinger (SignalBadge), Score (ScoreBadge)

**Performance tab**: Ticker, Annual Return (ChangeIndicator), Volatility (%), Sharpe Ratio (color-coded: ≥1 green, ≥0 default, <0 red), Score (ScoreBadge)

All tabs: Last column is `RefreshIndicator` per row. Sortable columns via `SortHeader` (click toggles asc/desc, active column shows ArrowUpDown icon in cyan).

### Grid View
Responsive grid of stock cards — each shows `Sparkline`, ticker (with Briefcase icon if held), `ScoreBadge`, `SignalBadge`, `RefreshIndicator`.

### Pagination
Static "Showing 1-N of N" + disabled prev/next buttons (pagination is UI shell only).

---

## 7. Stock Detail Page

**File**: `src/pages/StockDetail.tsx`  
**Route**: `/stocks/:ticker`

### Header
- Close button (← navigates back)
- Breadcrumb: Dashboard > {TICKER}
- Ticker (mono, 2xl bold) + `ScoreBadge` + company name + sector tag
- Watchlist toggle button (BookmarkCheck / Bookmark)
- Large price display (3xl mono bold) + `ChangeIndicator` + dollar change + `RefreshIndicator`

### Price Chart
- **Chart type toggle**: Line / Candle (with LineChart and CandlestickChart icons)
- **Timeframe selector**: 1M, 3M, 6M, 1Y, 5Y
- **Line chart**: AreaChart with cyan gradient fill, grid, axis labels
- **Candle chart**: ComposedChart with colored bars (green for bullish close≥open, red for bearish)
- Generated data: `generatePriceChart()` — OHLCV data from base price

### Benchmark Comparison
- Normalized % change comparison chart
- 3 lines: Stock (cyan solid), S&P 500 (green dashed), NASDAQ (amber dashed)
- Zero reference line
- Legend with colored dots

### Signal Breakdown (4 cards)
Each `SignalCard`:
- **RSI (14)**: Value, signal badge, meter bar (0-100), description of condition
- **MACD**: Value, signal badge, bullish/bearish description
- **SMA Crossover**: Signal badge (GOLDEN_CROSS / DEATH_CROSS / ABOVE_200 / BELOW_200), description
- **Bollinger**: Signal badge (UPPER / MIDDLE / LOWER), description

### Signal History Chart (90 days)
- Dual-axis ComposedChart: Composite Score (left, 0-10, cyan) + RSI (right, 0-100, amber dashed)

### Risk & Return (3 metric cards)
- Annual Return (color-coded)
- Volatility (neutral)
- Sharpe Ratio (green if ≥1, red if <0)

### Fundamentals (conditional — only if data exists for ticker)
- 4 metric cards: P/E Ratio, PEG Ratio, FCF Yield, Debt/Equity
- **Piotroski F-Score panel**:
  - Score display (X/9, color-coded)
  - 9-segment progress bar
  - 3×3 grid of individual criteria with check/X icons

### Dividends (conditional — only if data exists for ticker)
- 4 metric cards: Yield, Annual Dividends, Total Received, Payment Count
- Expandable "Payment History" table (date + amount per row)

---

## 8. Portfolio Page

**File**: `src/pages/Portfolio.tsx`  
**Route**: `/portfolio`

### Header
- "Portfolio" title
- Settings button → opens settings sheet
- "Log Transaction" button (cyan primary)

### KPI Tiles (4)
- Total Value ($3,370.15, cyan accent)
- Cost Basis
- Unrealized P&L (color-coded gain/loss accent)
- Return % (color-coded)

### Portfolio Value Chart
- AreaChart over 90 days with:
  - Portfolio value line (cyan gradient fill)
  - Cost basis line (gray dashed)
- Generated by `generatePortfolioHistory()`

### Positions Table (3/5 width)
Columns: Ticker, Shares, Avg Cost, Current, Market Val, P&L (ChangeIndicator), Return (ChangeIndicator), Weight (%), Alerts

**Alerts column**: Icon badges per alert:
- Critical (AlertOctagon, red) — stop-loss, position concentration
- Warning (AlertTriangle, amber) — sector concentration

### Transaction History (expandable)
- Collapsible via ChevronDown button
- Table: Date, Ticker, Type (BUY green / SELL red badge), Shares, Price, Total, Delete button (Trash2)

### Sector Allocation (2/5 width)
- `AllocationDonut` with full sector breakdown
- Alert banner: "Technology exceeds 30% sector limit (100%)" in red

### Rebalancing Panel
- Per-position row: Ticker, Current Weight → Target Weight, Action badge (AT_CAP / BUY_MORE)
- Target: Equal-weight across all positions

### Settings Sheet (slide-in from right)
- Backdrop overlay with blur
- 3 sliders:
  - Stop-loss threshold (default 20%)
  - Max position concentration (default 5%)
  - Max sector concentration (default 30%)
- Save button

### Log Transaction Modal
- Centered modal with backdrop
- Fields: Ticker, BUY/SELL toggle (green/gray buttons), Shares, Price per share, Date, Notes
- Submit button

---

## 9. Sectors Page

**File**: `src/pages/Sectors.tsx`  
**Route**: `/sectors`

### Header
- Breadcrumb: Dashboard > Sectors
- "Sector Performance" title
- **Portfolio Only toggle**: Filters to show only stocks in portfolio
- **Correlation toggle**: Enables correlation matrices within expanded sectors

### Sector Allocation Overview
- Large `AllocationDonut` with `MOCK_SECTORS_FULL` data (5 sectors)

### Sector Accordions
Each sector is a collapsible card:
- **Header row**: Color dot, sector name, stock count, avg score (color-coded), avg return (`ChangeIndicator`), chevron
- **Expanded content**:
  - Full comparison table: Ticker (linked, portfolio dot indicator), Name, Price, Change, Score, RSI, MACD, SMA, Return, Volatility, Sharpe, Freshness
  - Held stocks highlighted with `bg-primary/5`

### Correlation Matrix (per sector, when toggle is on)
Two view modes:
- **Heatmap**: Grid of cells colored by correlation strength. Click a row to highlight.
  - Color scale: 0-0.2 green, 0.2-0.4 light green, 0.4-0.6 amber light, 0.6-0.8 amber, 0.8+ red
- **Table**: Select a ticker → ranked list of correlations with interpretation text
  - Interpretations: "Very high — redundant diversification" down to "Very low — excellent diversification"

### Correlation Legend
- Color-coded bar explaining the 5 correlation ranges
- Explanation text about diversification benefits

---

## 10. AI Chat Panel

**File**: `src/components/shell/ChatPanel.tsx`

### Panel Behavior
- Width: 360px (slides in/out with transition)
- Toggled via "AI Analyst" button in Topbar or close (X) button in panel
- Opens to the right of the main content area

### States

**1. Agent Selection** (no messages, no agent chosen):
- Bot icon + "Choose an Agent"
- 2 buttons:
  - **Stock Analyst**: BarChart3 icon, cyan highlighted border, "Signals, portfolio, SEC filings, macro"
  - **General**: Globe icon, neutral, "News & web search only"

**2. Suggestion Chips** (agent chosen, no messages):
- Sparkles icon + "Stock Signal AI" title
- 4 suggestion buttons:
  - "Analyze my portfolio"
  - "Best signals today"
  - "What's happening with NVDA?"
  - "Top sector momentum"
- Clicking fills the input (does not auto-send)

**3. Chat Messages**:
- **User messages**: Right-aligned bubble, `bg-primary/15`, rounded with `rounded-br-md`
- **Assistant messages**: Left-aligned, prose styling. Supports:
  - Markdown tables (custom rendered)
  - Bold text
  - Numbered lists, bullet lists
  - Headings (h2, h3, h4)
- **Tool call cards**: Expandable cards above assistant message
  - Shows tool name (mono font), status icon (spinner/check/error), truncated result
  - Expanded: Full result text + Copy/CSV buttons

**4. Streaming state**: 3 pulsing cyan dots + "Analyzing your question..."

### Session Management
- Sessions list (toggleable via MessageSquare icon):
  - "New Chat" button
  - Session rows: Title, agent type badge (Stock/General), last message preview, expired flag, delete button (on hover)
- Loading a session populates demo messages

### Input Bar
- Textarea with auto-grow (max 6 rows)
- Enter to send, Shift+Enter for newline
- Send button (cyan) / Stop button (red square) when streaming

### Chat Header
- Bot icon with green online dot
- "AI Analyst" title + "Powered by Claude" subtitle
- Session toggle + Close buttons

---

## 11. Shared Components

### `Sparkline` (`src/components/shared/Sparkline.tsx`)
- Pure SVG polyline from numeric array
- Auto-scales to min/max of data
- Color: green if last > first, red otherwise
- Props: `data: number[]`, `width`, `height`, `strokeWidth`, `className`

### `ScoreBadge` (`src/components/shared/ScoreBadge.tsx`)
- Pill badge showing composite score (0-10)
- Color thresholds: ≥8 green, ≥5 amber, <5 red
- Sizes: xs (h-4), sm (h-5), md (h-6)
- Mono font, tabular-nums

### `ScoreBar` (`src/components/shared/ScoreBar.tsx`)
- 10-segment horizontal bar chart
- Filled segments colored by score threshold (same as ScoreBadge)
- Props: `score`, `max=10`, `segments=10`, `className`

### `SignalBadge` (`src/components/shared/SignalBadge.tsx`)
- Pill badge for any signal string
- Comprehensive style map covering 15+ signal values:
  - BULLISH, BEARISH, OVERSOLD, OVERBOUGHT, NEUTRAL
  - GOLDEN_CROSS, DEATH_CROSS, ABOVE_200, BELOW_200
  - UPPER, MIDDLE, LOWER
  - BUY, HOLD, SELL, WATCH, AVOID
- Custom labels for SMA signals (e.g., "Golden ×", "Above 200")
- Sizes: sm, md

### `ChangeIndicator` (`src/components/shared/ChangeIndicator.tsx`)
- Formatted numeric change display
- Green for positive, red for negative, muted for zero
- Configurable prefix ("$"), suffix ("%"), sign display
- Mono font, tabular-nums

### `RefreshIndicator` (`src/components/shared/RefreshIndicator.tsx`)
- Per-ticker refresh button with relative time display
- Reads from `StockRefreshContext`
- Shows: RefreshCw icon + "just now" / "5m ago" / "6h ago" / "2d ago"
- Stale detection: >12 hours = amber warning color
- Spinning animation during refresh
- Click handler calls `refreshStock(ticker)` with `stopPropagation` (works inside links)
- Compact mode: icon only, no text

### `AllocationDonut` (`src/components/shared/AllocationDonut.tsx`)
- CSS conic-gradient donut chart (no SVG/canvas)
- Shows sector colors with percentage labels
- Props: `sectors: SectorAllocation[]`, `size`, `holeRatio`
- Legend: Color dot + sector name + percentage

---

## 12. State Management & Contexts

### `ChatContext` (`src/contexts/ChatContext.tsx`)
- `chatOpen: boolean` — Whether the chat panel is visible
- `setChatOpen(open: boolean)` — Directly set state
- `toggleChat()` — Toggle open/close

### `StockRefreshContext` (`src/contexts/StockRefreshContext.tsx`)
Provides live, refreshable stock data across the entire app.

**State**:
- `stocks: Map<string, WatchlistStock>` — Current stock data by ticker
- `allStocks: WatchlistStock[]` — Ordered array
- `lastRefreshed: Record<string, Date>` — Per-ticker timestamps
- `refreshing: Record<string, boolean>` — Per-ticker loading state
- `refreshingAll: boolean`

**Actions**:
- `refreshStock(ticker)`: Simulates a single stock refresh (800-1400ms delay). Updates price, change, RSI, MACD, composite score, sparkline.
- `refreshAll()`: Staggered refresh of all stocks (150ms between each). Sets `refreshingAll` during bulk operation.

**Simulation logic** (`simulateStockRefresh`):
- Price: ±2% random walk (slight upward bias)
- RSI: ±3 random walk, clamped 5-95, re-derives signal
- MACD: ±0.25 random walk, re-derives signal
- Composite score: ±0.2 random walk, clamped 0-10
- Sparkline: Regenerated from new price

**Initial staleness**: First 2 stocks refreshed 30min ago, next 3 at 6h ago, rest at 1+ days — creates visual variety in RefreshIndicator.

---

## 13. Data Model & Types

### `WatchlistStock`
```typescript
{
  ticker: string;           // e.g., "AAPL"
  name: string;             // e.g., "Apple Inc."
  sector: string;           // e.g., "Technology"
  price: number;            // Current price
  change: number;           // Dollar change
  changePct: number;        // Percentage change
  compositeScore: number;   // 0-10 composite signal score
  rsiValue: number;         // RSI value (0-100)
  rsiSignal: "OVERSOLD" | "NEUTRAL" | "OVERBOUGHT";
  macdValue: number;        // MACD histogram value
  macdSignal: "BULLISH" | "BEARISH";
  smaSignal: "GOLDEN_CROSS" | "ABOVE_200" | "BELOW_200" | "DEATH_CROSS";
  bbPosition: "UPPER" | "MIDDLE" | "LOWER";
  annualReturn: number;     // Annual return %
  volatility: number;       // Annualized volatility %
  sharpe: number;           // Sharpe ratio
  priceHistory: number[];   // 30-point sparkline data
  recommendation?: "BUY" | "WATCH" | "AVOID";
}
```

### `Position`
```typescript
{
  ticker: string;
  name: string;
  sector: string;
  shares: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  weight: number;           // Portfolio weight %
  alerts: PositionAlert[];
}
```

### `PositionAlert`
```typescript
{
  type: "stop_loss" | "position_concentration" | "sector_concentration" | "weak_fundamentals";
  severity: "critical" | "warning";
  message: string;
}
```

### `Recommendation`
```typescript
{
  ticker: string;
  action: "BUY" | "WATCH" | "AVOID" | "HOLD" | "SELL";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  compositeScore: number;
  reasoning: string;
}
```

### `IndexInfo`
```typescript
{
  name: string;
  slug: string;
  stockCount: number;
  description: string;
  value?: number;
  changePct?: number;
  sparkline?: number[];
}
```

### `SectorAllocation`
```typescript
{
  sector: string;
  pct: number;
  color: string;        // HSL color string
  overLimit?: boolean;
}
```

### `FundamentalData`
```typescript
{
  pe: number;           // P/E ratio
  peg: number;          // PEG ratio
  fcfYield: number;     // Free cash flow yield %
  debtEquity: number;   // Debt/equity ratio
  piotroski: number;    // F-Score (0-9)
  piotroskiBreakdown: { name: string; passed: boolean }[];
}
```

### `DividendData`
```typescript
{
  yield: number;
  annualDividends: number;
  totalReceived: number;
  paymentCount: number;
  history: { date: string; amount: number }[];
}
```

### `ChatMessage`
```typescript
{
  id: string;
  role: "user" | "assistant";
  content: string;       // Markdown-formatted
  toolCalls?: ToolCall[];
  timestamp: Date;
}
```

### `ToolCall`
```typescript
{
  id: string;
  name: string;          // e.g., "get_portfolio_positions"
  status: "running" | "completed" | "error";
  params?: Record<string, unknown>;
  result?: string;
  error?: string;
}
```

### `ChatSession`
```typescript
{
  id: string;
  title: string;
  agentType: "stock" | "general";
  lastMessage: string;
  createdAt: Date;
  expired?: boolean;
}
```

### `Transaction`
```typescript
{
  id: string;
  ticker: string;
  type: "BUY" | "SELL";
  shares: number;
  pricePerShare: number;
  total: number;
  date: string;
  notes?: string;
}
```

### `StatTileData`
```typescript
{
  label: string;
  value: string;
  subValue?: string;
  change?: string;
  changeType?: "gain" | "loss" | "neutral";
  accent?: "cyan" | "gain" | "loss" | "warning";
  type?: "donut" | "signal-summary";
}
```

---

## 14. Mock Data Layer

**File**: `src/lib/mock-data.ts`

### Stocks (10 total)
| Ticker | Sector | Score | Recommendation |
|--------|--------|-------|----------------|
| AAPL | Technology | 3.1 | WATCH |
| MSFT | Technology | 3.4 | WATCH |
| NVDA | Technology | 3.4 | AVOID |
| GOOGL | Technology | 4.1 | BUY |
| TSLA | Technology | 2.6 | AVOID |
| AMZN | Consumer | 6.4 | WATCH |
| META | Technology | 8.1 | BUY |
| JPM | Financials | 5.8 | WATCH |
| UNH | Healthcare | 4.2 | AVOID |
| XOM | Energy | 3.5 | AVOID |

### Positions (2)
- AAPL: 10 shares, avg $195.50, +26.8%, 73.6% weight. Alerts: position concentration, sector concentration.
- NVDA: 5 shares, avg $880.00, -79.8%, 26.4% weight. Alerts: stop-loss, position concentration.

### Market Indexes (3)
- S&P 500: 5,321.40 (+0.82%)
- NASDAQ-100: 18,672.10 (+1.15%)
- Dow 30: 39,412.80 (-0.23%)

### Sectors (5 for full allocation)
Technology 42%, Healthcare 18%, Financials 15%, Consumer 13%, Energy 12%

### Fundamentals (AAPL only)
PE: 28.5, PEG: 1.2, FCF Yield: 3.8%, D/E: 1.45, Piotroski: 7/9

### Dividends (AAPL only)
Yield: 0.52%, 5 quarterly payments of $0.24

### Chat Sessions (3)
Portfolio Analysis, NVDA Deep Dive, Market Overview (expired)

### Helper Functions
- `spark(base, volatility, trend, n=30)`: Generates sparkline data array
- `simulateStockRefresh(stock)`: Returns new WatchlistStock with randomized updates

---

## 15. Routing

**File**: `src/App.tsx`

| Route | Component | Layout |
|-------|-----------|--------|
| `/` | Dashboard | ShellLayout |
| `/screener` | Screener | ShellLayout |
| `/stocks/:ticker` | StockDetail | ShellLayout |
| `/portfolio` | Portfolio | ShellLayout |
| `/sectors` | Sectors | ShellLayout |
| `/login` | Login | Standalone (no shell) |
| `/register` | Register | Standalone (no shell) |
| `*` | NotFound | Standalone |

ShellLayout routes are wrapped in `StockRefreshProvider` and `ChatProvider` contexts.

---

## Appendix: Component Dependency Map

```
ShellLayout
├── SidebarNav (logo, nav items, logout)
├── Topbar (breadcrumb, search, market status, signals, bell, AI toggle)
├── ChatPanel (agent selector, suggestions, messages, tool cards, sessions)
└── <Outlet>
    ├── Dashboard
    │   ├── AllocationDonut, Sparkline, ScoreBadge, ScoreBar
    │   ├── SignalBadge, ChangeIndicator, RefreshIndicator
    │   └── IndexCard, RecommendationRow (sub-components)
    ├── Screener
    │   ├── FilterSelect, SortHeader
    │   ├── ScreenerTable (all shared badges)
    │   └── ScreenerGrid
    ├── StockDetail
    │   ├── AreaChart, ComposedChart, BarChart (recharts)
    │   ├── SignalCard, MetricCard
    │   └── All shared badges
    ├── Portfolio
    │   ├── AreaChart (recharts)
    │   ├── AllocationDonut, ChangeIndicator
    │   ├── KpiTile, SettingSlider, ModalInput
    │   └── Settings sheet, Transaction modal
    └── Sectors
        ├── AllocationDonut, ScoreBadge, SignalBadge
        ├── ChangeIndicator, RefreshIndicator, Sparkline
        └── CorrelationHeatmap (sub-component)
```
