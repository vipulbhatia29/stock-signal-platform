# Reusable Design Principles — Financial & Data-Dense UIs

Cross-project reference for building professional financial dashboards and data-heavy applications.
Extracted from research on TradingView, Robinhood, Bloomberg Terminal, and financial UX best practices.

---

## Color System

- **Max 5-6 colors** to avoid clutter. Muted tones for backgrounds, bright colors reserved for semantic meaning only.
- **Gain/loss colors are sacred** — green/red used ONLY for positive/negative financial movement. Never for unrelated UI states.
- **Never rely on color alone** — always pair with icon (arrow/trend), text sign (+/-), or pattern. ~5% of users have color vision deficiency.
- **Blue/orange is deuteranopia-safe** — offer as alternative to green/red when building accessible modes.
- **Dark mode contrast**: minimum 4.5:1 (WCAG AA) for all text; 7:1 for critical financial numbers.
- **Avoid pure black/white in dark mode** — use dark grays with subtle blue undertone (reduces eye strain), off-white text (reduces glare).
- **Use OKLCH color space** for perceptually uniform color manipulation. HSL is unreliable for perceived brightness.
- **CSS variables for semantic colors** — define `--gain`, `--loss`, `--neutral` etc. in both light/dark themes. Components reference semantics, not raw values.

## Typography

- **1-2 fonts maximum**. Use weight variation for hierarchy, not additional typefaces.
- **`tabular-nums` on ALL numeric displays** — ensures column alignment in tables and prevents layout shift during updates.
- **Sans-serif for UI text, monospace for ticker symbols only** (not prices — tabular-nums on sans is better for numbers).
- **Semantic type scale**: define named constants (PAGE_TITLE, METRIC_PRIMARY, TABLE_NUM) rather than ad-hoc sizing.

## Layout & Information Density

- **Inverted pyramid** — most critical data at top-left (natural scan direction for LTR languages).
- **Limit primary dashboard to 4-5 key visualizations/metrics** — more causes cognitive overload.
- **Card-based layouts** with mini-graphs (sparklines) inside cards for at-a-glance trends.
- **"Just enough distance" between cards** — consistent gaps prevent cognitive overload without wasting space.
- **Data-ink ratio principle** (Tufte): remove all non-informational visual elements. Every pixel must justify its existence.
- **UI density = value / (time x space)** — optimize for information conveyed per second per pixel.
- **Mobile: stacked scrolling** — first view is always the summary. Progressive disclosure for details.

## Charts & Data Visualization

- **Line charts for time trends**, bar charts for comparisons, heatmaps for correlations.
- **Interactive crosshair hover** is expected in financial charts — not optional.
- **Sentiment-tinted chart areas** — subtle background gradient matching gain/loss direction (Robinhood pattern).
- **Period selector buttons directly above chart** — not in a separate control panel.
- **Chart colors need runtime resolution** — if using CSS variables with Recharts/D3/etc., read via `getComputedStyle` at runtime. Most chart libraries can't resolve CSS `var()` references.
- **Responsive chart heights** — taller on desktop (400px), shorter on mobile (250px). Never fixed.
- **Skeleton loaders that match content dimensions** — prevent layout shift and give accurate loading feedback.

## Tables & Screeners

- **Column preset tabs** — pre-built column groupings (Overview, Signals, Performance) switchable with one click (TradingView pattern).
- **Dual-view mode** — toggle between data table and chart grid view (miniature sparkline cards per item).
- **Sticky headers** with background blur for long scrollable tables.
- **Full-row click** navigates to detail — not just a link in one column.
- **Density toggle** — comfortable (default) and compact modes. Persist user preference.
- **Sparklines in table rows/cards** — inline mini-charts for at-a-glance trend context.
- **Sort indicators must be bold and obvious** — not tiny chevrons.

## Dark Mode (Bloomberg-Inspired)

- **Design for dark first, adapt to light** — traders and power users prefer dark mode.
- **Dark background with subtle blue undertone** — not pure black. `oklch(0.145 0.005 250)` is a good starting point.
- **Card surfaces slightly elevated** from background for depth.
- **Increase chart color lightness** (L >= 0.70 in OKLCH) so data lines pop against dark backgrounds.
- **Shift gain/loss hues for dark backgrounds** — green toward cyan-green (hue ~148), red toward orange-red (hue ~22) for better contrast.

## Animation

- **Staggered fade-in for card/row entry** — 30-80ms delay per item, cap at 12 items (below-fold items don't need animation).
- **`prefers-reduced-motion` MUST be respected** — collapse all animations to near-zero duration.
- **NO number ticking, NO chart drawing animations, NO route transitions** — these feel gimmicky in financial UIs.
- **Skeleton-to-content transition**: subtle fade, 200ms. Consistent across all loading states.

## Accessibility

- **Every gain/loss indicator**: color + icon + sign (triple redundancy).
- **Charts**: `role="img"` + descriptive `aria-label`.
- **Score badges**: `aria-label="Composite score 7.5 out of 10, bullish"`.
- **Tables**: proper `scope` on `<th>`, keyboard-navigable rows.
- **Never use color as the sole differentiator** for any information.

## Component Patterns

- **ChangeIndicator** — colored arrow + signed value + aria-label. The single source of truth for gain/loss display.
- **MetricCard** — standardized KPI block (label + value + optional change). Use everywhere metrics appear.
- **SignalMeter** — segmented score bar. Color-coded segments, `role="meter"` with aria attributes.
- **ErrorState + EmptyState** — always provide both. Error includes retry action.
- **Breadcrumbs** on detail pages for navigation context.

---

## Sources

- TradingView Stock Screener UX documentation
- Robinhood mobile UI/UX analysis (WorldBusinessOutlook, LinkedIn, IXD@Pratt)
- Bloomberg Terminal UX: "Concealing Complexity", Color Accessibility, Launchpad redesign
- Matt Strom — "UI Density"
- Fintech Dashboard Design (Merge Rocks, QodeQuay, Phoenix Strategy Group)
- Financial Dashboard UI/UX Design Principles 2025
