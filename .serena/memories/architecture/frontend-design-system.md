---
scope: project
category: architecture
---

# Frontend Design System

## Phase 4A: Dark Navy Command-Center Shell
- `forcedTheme="dark"` on ThemeProvider — no light mode toggle.
- Navy token palette: bg-navy-950/900/800/700, text-navy-100/200/400.
- Components: SidebarNav, Topbar, ChatPanel (stub), StatTile, AllocationDonut, PortfolioDrawer, Sparkline.

## Color System for Recharts
- Recharts requires literal color strings — CSS variables (hsl(var(--x))) don't resolve.
- Use `useChartColors()` hook (reads via `getComputedStyle`) or local `readCssVar()` for one-off reads.
- Lazy `useState(() => resolveColor(...))` for colors needing initial paint.

## Shared Components
- `ChangeIndicator`, `SectionHeading`, `ChartTooltip`, `ErrorState`, `Breadcrumbs`
- `Sparkline` (SVG, no Recharts — for inline sparklines in tables)
- `SignalMeter`, `MetricCard`, `PortfolioValueChart`
- `DensityProvider` — screener compact/comfortable toggle
- `ForecastCard` — 3 horizon pills (90/180/270d), confidence badge, Sharpe direction
- `AlertBell` — Popover dropdown, unread badge count, mark-all-read
- `ScorecardModal` — Dialog with hit rate, alpha, per-horizon breakdown, worst miss

## shadcn/base-ui v4 Gotchas
- `SheetTrigger`, `PopoverTrigger` use `render={<Button />}` prop, NOT `asChild`.
- Applies to ALL base-ui trigger components.

## Testing
- Jest: `testEnvironment: "jsdom"` (NOT "node").
- `@testing-library/react` + `@testing-library/jest-dom`.
- Test files at `frontend/src/__tests__/`.
