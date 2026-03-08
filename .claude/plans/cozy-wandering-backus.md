# Design System Plan — Stock Signal Platform

## Context

The frontend has all pages built (dashboard, screener, stock detail, auth) but lacks a cohesive design system. Colors, typography, spacing, and component patterns are ad-hoc — sentiment colors are hardcoded Tailwind strings, chart colors reference `hsl()` but CSS variables use OKLCH (broken), no responsive breakpoints on signal/metric grids, no breadcrumbs, and no reusable financial-specific components (gain/loss indicators, sparklines, KPI cards). This plan creates a formal design system optimized for financial data visualization, informed by patterns from TradingView, Robinhood, and Bloomberg Terminal.

---

## Research Findings — TradingView, Robinhood, Bloomberg Terminal

### TradingView (Professional Trader Tool)

**Screener design:**
- **Filter-first architecture** — Filters sit prominently at top in a dedicated panel with search. Categories: Security Info, Market Data, Technicals, Financials, Dividends
- **Tab-based column presets** — Pre-built column groupings (Overview, Performance, Valuation, Extended Hours) switchable with one click. Users can create custom column sets via "+" button
- **Dual-view mode** — Toggle between data table rows and a chart grid view (miniature charts per stock). Chart grid has configurable interval and chart type
- **Progressive disclosure** — Basic filters shown upfront; advanced/technical filters accessible through dedicated dialog
- **Sparklines in watchlist** — Advanced watchlist mode shows inline mini-charts beside each symbol
- **Save & alert** — Filter+column layouts saveable as templates; filter criteria convertible to automated alerts
- **Column-level customization** — Right-click any column header for settings, time period selection, sort direction

**Key patterns to adopt:**
1. Column preset tabs above screener table (Overview | Signals | Performance | Valuation)
2. Chart grid toggle as alternative to table view
3. Inline sparklines in watchlist items
4. Filter-as-alert pattern (future feature)

### Robinhood (Consumer-First Design)

**Color as emotional intelligence:**
- Green = portfolio gains, positive movement → "confidence, optimism"
- Red = losses, negative movement → "urgency, caution"
- Grey = after-hours/unavailable data → "neutrality, calm"
- Light green = healthy account balance → "reassurance"
- Blue = interactive elements, pending actions → "trust, clarity"
- Dynamic color feedback: entire chart background tints green/red based on portfolio direction

**Stock detail page:**
- Card-based modular system — tap card to expand into charting, news, buy opportunities
- Three distinct action buttons (Buy/Sell/Options) replaced ambiguous single "Trade" button
- Each button dynamically shows bid/ask price in real-time
- Micro-interactions: odometer effects for real-time price updates

**Dashboard layout:**
- Hero element: large portfolio performance line chart (full-width)
- Timeframe toggles: 1 Day, 1 Week, 1 Month, 3 Months, 1 Year, All
- Card-based watchlist below with one-action-at-a-time navigation
- "Just enough distance" between cards to prevent cognitive overload

**Design critiques (what to avoid):**
- Missing custom time range selector (users want flexible date picking)
- No asset allocation/diversification view on main screen
- Limited analysis tools — fine for consumers, insufficient for our signal-analysis use case

**Key patterns to adopt:**
1. Sentiment-colored chart areas (subtle background tint matching gain/loss)
2. Three-button action pattern for clear affordances
3. Card spacing discipline — consistent gaps, no cognitive overload
4. Period selector buttons directly above chart (not in a separate control)

### Bloomberg Terminal (Information Density Master)

**Data density philosophy:**
- Single screen shows: scrolling sparklines of indices, trading volume breakdowns, tables with dozens of columns, scrolling news headlines, keyboard shortcuts — all simultaneously
- "The secret to dealing with increasing complexity is to conceal it from the user"
- Data loads "almost instantaneously" — speed is the "real superpower"
- UI density = value / (time × space). Every pixel must justify its existence

**Dark mode as brand:**
- Iconic amber-on-black evolved to modern dark theme
- Dark background is default, not an option — "hallmark of being a financial superpower"
- Colors like bright blue and bright orange stand out against dark backgrounds
- High-contrast text for data readability is paramount

**Layout system:**
- Tabbed panel model replaced old 4-panel maximum
- Users can resize windows to see more/fewer rows and columns
- Fully customizable arrangement of connected applications across multi-display setups
- Consistency across thousands of functions is critical for navigation

**Color accessibility (from their UX team):**
- Bloomberg specifically designed Terminal colors for accessibility
- Never rely on color alone — always pair with shape, text, or pattern

**Key patterns to adopt:**
1. Dark-mode-first design (traders prefer it; design for dark, adapt to light)
2. Tabbed panel concept for screener column presets
3. High temporal density — minimize loading times, use skeletons that exactly match content
4. Data-ink ratio principle: remove all non-informational visual elements
5. Consistent patterns across all views (same heading style, same card style, same table style)

### Cross-Platform Best Practices (2025 Financial Dashboard Research)

**Color system:**
- Maximum 5-6 colors to avoid clutter
- Muted tones for background, bright green/red reserved for gain/loss only
- Minimum 4.5:1 contrast ratio (WCAG AA); 7:1 for critical financial data
- ~5% of users have color vision deficiency — never use color alone
- Blue/orange is deuteranopia-safe alternative to green/red
- Avoid pure black (#000) backgrounds in dark mode — use dark grays (reduces eye strain)
- Avoid pure white (#FFF) text in dark mode — use off-whites

**Layout:**
- Inverted pyramid: most critical data at top-left (natural scan direction)
- Limit primary dashboard to 4-5 key visualizations/metrics
- Card-based layouts with mini-graphs inside cards for at-a-glance trends
- Mobile: scrolling stacked approach, first view is always the summary

**Charts:**
- Line charts for time trends, bar charts for comparisons
- Heatmaps for correlation matrices
- Waterfall charts for P&L breakdowns
- Interactive charts with crosshair hover are expected

**Typography:**
- 1-2 fonts maximum; use weight variation for hierarchy, not additional typefaces
- Sans-serif for UI; monospace for tickers/codes only
- `tabular-nums` for all numeric displays (column alignment)

---

## 1. Color System Overhaul

### 1.1 Add Financial Semantic CSS Variables (`globals.css`)

Add to both `:root` and `.dark` scopes:

| Variable | Purpose | Light (OKLCH) | Dark (OKLCH) |
|---|---|---|---|
| `--gain` | Positive returns | `oklch(0.55 0.17 145)` | `oklch(0.72 0.18 148)` |
| `--gain-foreground` | Text on gain bg | `oklch(0.25 0.08 145)` | `oklch(0.95 0.05 148)` |
| `--loss` | Negative returns | `oklch(0.55 0.20 25)` | `oklch(0.72 0.19 22)` |
| `--loss-foreground` | Text on loss bg | `oklch(0.25 0.10 25)` | `oklch(0.95 0.05 22)` |
| `--neutral-signal` | Hold/neutral | `oklch(0.65 0.15 80)` | `oklch(0.78 0.14 82)` |
| `--chart-price` | Price line | Blue | Bright blue |
| `--chart-volume` | Volume bars | Gray-blue 30% | Gray 40% |
| `--chart-sma-50` | 50-day SMA | Orange | Warm orange |
| `--chart-sma-200` | 200-day SMA | Purple | Light purple |
| `--chart-rsi` | RSI line | Coral | Light coral |

Register all in `@theme inline` block so Tailwind generates `text-gain`, `bg-loss`, etc.

### 1.2 Fix OKLCH/HSL Mismatch

Charts currently use `hsl(var(--chart-1))` but variables are OKLCH. Create a `useChartColors()` hook that reads CSS variables via `getComputedStyle` at runtime, updating on theme change.

### 1.3 Migrate Sentiment Colors (`lib/signals.ts`)

Replace hardcoded Tailwind class maps:
```ts
// Before: "text-emerald-700 dark:text-emerald-400"
// After:  "text-gain"
```

### 1.4 Accessibility — Color-Blind Safe (Bloomberg + WCAG research)

Every gain/loss indicator must combine color + icon (TrendingUp/TrendingDown) + sign (+/-). Never rely on green/red alone. Bloomberg's UX team specifically designs for this — we adopt the same principle.

- Primary: green/red with icon+sign redundancy
- Future: optional blue/orange mode toggle for deuteranopia users
- Minimum contrast: 4.5:1 (AA) for all text; 7:1 for critical financial numbers

---

## 2. Typography System

### 2.1 Semantic Type Scale

Create `lib/typography.ts` with named constants:

| Token | Classes | Usage |
|---|---|---|
| `PAGE_TITLE` | `text-2xl font-semibold tracking-tight` | Page headings |
| `SECTION_HEADING` | `text-sm font-medium uppercase tracking-wider text-muted-foreground` | Section labels |
| `METRIC_PRIMARY` | `text-2xl font-semibold tabular-nums` | Key values ($189.42) |
| `METRIC_SECONDARY` | `text-xl font-semibold tabular-nums` | Signal values |
| `TICKER` | `font-mono text-base font-semibold` | AAPL, MSFT |
| `TABLE_NUM` | `text-sm tabular-nums` | All table numerics |

### 2.2 Font Rules

- **Geist Sans**: All UI text. Use `tabular-nums` for number alignment.
- **Geist Mono**: Ticker symbols only (not prices — tabular-nums on sans is better).

---

## 3. Responsive Layout Fixes

| Component | Current | Fix |
|---|---|---|
| Signal cards | `grid-cols-2` always | `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4` |
| Risk/Return metrics | `grid-cols-3` always | `grid-cols-1 sm:grid-cols-3` |
| Chart heights | Fixed 400px/300px | `h-[250px] sm:h-[400px]` / `h-[200px] sm:h-[300px]` |
| Screener table | No sticky header | Add `sticky top-0 z-10 bg-background` to thead |

---

## 4. Screener Enhancements (TradingView-Inspired)

### 4.1 Column Preset Tabs
Add tab bar above screener table: **Overview** | **Signals** | **Performance** | **Valuation**
- Each tab shows a different column set (like TradingView's column presets)
- Overview: Ticker, Name, Sector, Price, Change%, Score
- Signals: Ticker, RSI, MACD, SMA, Bollinger, Score
- Performance: Ticker, 1D%, 1W%, 1M%, 3M%, 1Y%, Sharpe
- Valuation: (future — needs fundamental data endpoints)
- Use shadcn `Tabs` component for the switcher

### 4.2 Enhanced Table Interactions
- **Sticky header** with background blur (like NavBar pattern)
- **Full-row click** navigates to stock detail (not just ticker link)
- **Row hover highlight** with subtle background change
- **Sortable columns** with clear sort direction indicators (current: small chevrons; improve: bolder arrows + sorted column header highlight)
- **Alternating row tints** in compact mode for scanability

### 4.3 Screener Density
- Default "comfortable" spacing matches current
- Future: compact mode reduces row height from 48px→36px, padding from p-4→p-2

---

## 5. New Components

### 5.1 `ChangeIndicator` — Gain/loss display
Props: `{ value: number | null; format: "percent" | "currency"; size?: "sm" | "default" }`
Renders: colored arrow icon + signed value. Accessible via `aria-label`.

### 5.2 `SectionHeading` — Extracted section label
Props: `{ children: ReactNode; action?: ReactNode }`
Replaces 6+ inline repetitions of the section heading pattern.

### 5.3 `ChartTooltip` — Reusable tooltip
Props: `{ label: string; items: { name, value, color }[] }`
Replaces duplicated tooltip render functions in PriceChart and SignalHistoryChart.

### 5.4 `ErrorState` — Error display with retry
Props: `{ error: string; onRetry?: () => void }`
Companion to existing EmptyState.

### 5.5 `Breadcrumbs` — Back navigation
For stock detail: `Dashboard > AAPL`. Uses referrer or search params.

### 5.6 `MetricCard` — Standardized KPI card (deferred)
Props: `{ label, value, change?, icon?, sentiment? }`
Replaces ad-hoc metric rendering in RiskReturnCard and IndexCard.

### 5.7 `Sparkline` — Tiny inline chart (deferred)
Props: `{ data: number[]; width?; height?; sentiment? }`
For table cells and stock cards. Recharts `<Line>` with no axes/grid.

### 5.8 `SignalMeter` — Visual score gauge (deferred)
Props: `{ score: number | null; size?: "sm" | "default" }`
Horizontal segmented bar showing composite score 0-10 with gradient.

---

## 6. Chart Design System (Robinhood + TradingView Patterns)

### 6.1 Create `lib/chart-theme.ts`
- Grid, axis, tooltip styling constants
- `useChartColors()` hook — reads CSS variables, updates on theme change
- Color map for each data series type

### 6.2 Standardize Both Charts
- Use `chart-theme.ts` constants for grid, axes, tooltips
- Use `ChartTooltip` component
- Responsive heights
- Crosshair cursor styling (`strokeDasharray: "4 2"` on Tooltip cursor)

### 6.3 Robinhood-Inspired Chart Patterns
- **Sentiment-tinted chart area**: subtle green/red gradient fill based on overall trend direction (like Robinhood's portfolio chart)
- **Period selector buttons directly above chart** (already have this — keep it)
- **Chart tooltip**: show date, price, volume, daily change% in a clean card format

---

## 7. Dark Mode Tuning (Bloomberg-Inspired)

Bloomberg's dark mode is iconic — the "hallmark of a financial superpower." Our dark mode should be the premium experience, not an afterthought.

- **Background**: avoid pure black — use `oklch(0.145 0.005 250)` (subtle blue undertone, reduces eye strain vs pure achromatic)
- **Card surfaces**: `oklch(0.195 0.005 250)` — slightly elevated from background
- **Text**: off-white `oklch(0.93 0 0)` for data, not pure white (reduces glare)
- **Chart colors**: increase lightness (L >= 0.70) so lines/bars pop against dark backgrounds
- **Gain/loss colors**: shift hues slightly — green toward cyan-green (hue ~148), red toward orange-red (hue ~22) for better dark-bg contrast
- **Borders**: `oklch(1 0 0 / 12%)` (slightly more visible than current 10%)
- Replace text "Dark"/"Light" toggle with Sun/Moon lucide icons

---

## 8. Animation (Minimal)

- Card entry: staggered `fade-in slide-in-from-bottom-2` (tw-animate-css already installed)
- Skeleton→content: `fade-in duration-200`
- Sentiment badge: `transition-colors duration-200`
- Price flash keyframes: CSS-only, for future WebSocket use
- `prefers-reduced-motion` media query to disable all
- **NO** number ticking, **NO** chart animation, **NO** route transitions

---

## 9. Accessibility

- All gain/loss: color + icon + sign (color-blind safe)
- Charts: `role="img"` + descriptive `aria-label`
- Badges: `aria-label="Composite score 7.5 out of 10, bullish"`
- Tables: proper `scope` on `<th>`, keyboard-navigable rows
- `prefers-reduced-motion` respected

---

## 10. Files to Create

```
frontend/src/lib/design-tokens.ts       # CSS var names as constants
frontend/src/lib/chart-theme.ts         # Recharts theme + useChartColors
frontend/src/lib/typography.ts          # Semantic class constants
frontend/src/components/change-indicator.tsx
frontend/src/components/chart-tooltip.tsx
frontend/src/components/error-state.tsx
frontend/src/components/breadcrumbs.tsx
frontend/src/components/section-heading.tsx
```

## 11. Files to Modify

| File | Changes |
|---|---|
| `globals.css` | Financial color vars, chart vars, flash keyframes, reduced-motion |
| `lib/signals.ts` | Migrate to CSS variable classes |
| `price-chart.tsx` | chart-theme, fix hsl→oklch, ChartTooltip, responsive height |
| `signal-history-chart.tsx` | Same chart-theme migration |
| `signal-cards.tsx` | Responsive grid, SectionHeading, density padding |
| `risk-return-card.tsx` | Responsive grid, ChangeIndicator |
| `screener-table.tsx` | Sticky header, row click, ChangeIndicator |
| `stock-header.tsx` | Breadcrumbs, ChangeIndicator |
| `score-badge.tsx` | aria-label |
| `signal-badge.tsx` | aria-label |
| `nav-bar.tsx` | Sun/Moon icons |
| Dashboard + stock detail pages | SectionHeading usage |

---

## 12. Implementation Phases

### Phase A: Foundation (do first — everything depends on it)
1. Add financial color CSS variables to `globals.css`
2. Register in `@theme inline` for Tailwind class generation
3. Fix OKLCH/HSL chart color mismatch
4. Create `lib/design-tokens.ts`, `lib/chart-theme.ts`, `lib/typography.ts`
5. Migrate `lib/signals.ts` to CSS variable classes
6. Build `useChartColors()` hook

### Phase B: Core Components
7. `ChangeIndicator`
8. `SectionHeading` + replace all inline heading patterns
9. `ChartTooltip` + refactor both charts
10. `ErrorState`
11. `Breadcrumbs` + add to stock detail

### Phase C: Responsive & Polish
12. Fix signal cards grid (1/2/4 cols)
13. Fix risk/return grid (1/3 cols)
14. Responsive chart heights
15. aria-labels on ScoreBadge, SignalBadge
16. Sticky screener table header

### Phase D: Dark Mode & Visual Polish
17. Bloomberg-inspired dark mode tuning
18. Sun/Moon theme toggle icons
19. Chart color brightness for dark mode
20. Entry animations + reduced-motion query

### Deferred (Phase 2.5+)
21. Column preset tabs (TradingView-inspired: Overview | Signals | Performance)
22. `MetricCard`, `Sparkline`, `SignalMeter` components
23. Sentiment-tinted chart gradient (Robinhood-style)
24. DensityProvider (compact/comfortable toggle)
25. Chart grid view toggle for screener

---

## Verification

After each phase:
1. `cd frontend && npm run build` — no TypeScript errors
2. `cd frontend && npm run lint` — no lint errors
3. Visual check in browser: light mode + dark mode
4. Verify chart colors render correctly in both themes
5. Check mobile responsiveness at 375px, 768px, 1280px widths
6. Run Lighthouse accessibility audit on dashboard page

---

## Sources

- [TradingView Stock Screener Walkthrough](https://www.tradingview.com/support/solutions/43000718885-tradingview-screeners-walkthrough/)
- [TradingView Stock Screener: Trade Smarter](https://www.tradingview.com/support/solutions/43000718866-tradingview-stock-screener-trade-smarter-not-harder/)
- [TradingView Screener Filters](https://www.tradingview.com/support/solutions/43000718745-how-to-use-filters-in-screener/)
- [TradingView Watchlist Advanced View](https://www.tradingview.com/support/solutions/43000771546-watchlist-advanced-view-mode/)
- [How Robinhood UI Balances Simplicity and Strategy](https://worldbusinessoutlook.com/how-the-robinhood-ui-balances-simplicity-and-strategy-on-mobile/)
- [Robinhood UX/UI Design Shaping Future of Investing](https://www.linkedin.com/pulse/how-robinhoods-uxui-design-shaping-future-investing-johnson-jr--srljc)
- [Design Critique: Robinhood iOS App — IXD@Pratt](https://ixd.prattsi.org/2025/02/design-critique-robinhood-ios-app/)
- [Bloomberg Terminal UX: Concealing Complexity](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/)
- [Bloomberg: Designing Terminal for Color Accessibility](https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/)
- [Bloomberg UX: Relaunching Launchpad](https://www.bloomberg.com/ux/2017/11/10/relaunching-launchpad-disguising-ux-revolution-within-evolution/)
- [UI Density — Matt Ström-Awn](https://mattstromawn.com/writing/ui-density/)
- [Fintech Dashboard Design — Merge Rocks](https://merge.rocks/blog/fintech-dashboard-design-or-how-to-make-data-look-pretty)
- [Best Color Palettes for Financial Dashboards](https://www.phoenixstrategy.group/blog/best-color-palettes-for-financial-dashboards)
- [Dark Mode Dashboard Design Principles](https://www.qodequay.com/dark-mode-dashboards)
- [Financial Dashboard UI/UX Design Principles 2025](https://medium.com/@allclonescript/20-best-dashboard-ui-ux-design-principles-you-need-in-2025-30b661f2f795)
