# UI Redesign + Phase 4 Shell — Design Spec

**Date:** 2026-03-15
**Branch:** `feat/phase-4-ai-chatbot`
**Status:** Approved — ready for implementation planning

---

## Overview

Replace the current light-mode top-navbar UI with a command-center dark theme: navy backgrounds, electric cyan accents, icon-only sidebar, resizable AI chat panel docked to the right. This is a two-phase implementation:

- **Phase A (Shell):** Design tokens, typography, sidebar layout, chat panel shell
- **Phase B (Components):** Restyle all existing components to match the new design system

The AI chat panel is wired as a UI shell in this spec. Phase 4 backend (LangGraph agents, streaming router) plugs into it separately.

---

## Reference

The approved visual reference is the static prototype at `prototype-ui.html` (project root). All visual decisions in this spec derive from that file.

Key design variables from the prototype:
```
Background:   #070d18   (CSS class: bg-background, var --background)
Card:         #0b1525   (CSS class: bg-card, var --card)
Card-2:       #0f1d32   (CSS class: bg-card2, var --card2)
Hover:        #121f33   (CSS class: bg-hov, var --hov)
Border:       rgba(255,255,255,0.07)   (var --b / --border)
Border-hi:    rgba(56,189,248,0.22)    (var --bhi)
Text-1:       #e8f0ff   (CSS class: text-foreground, var --foreground)
Text-2:       #6a80a8   (CSS class: text-muted-foreground, var --muted-foreground)
Text-3:       #2d3e5a   (CSS class: text-subtle, var --subtle)
Cyan accent:  #38bdf8   (CSS class: text-cyan / bg-cyan, var --cyan)
Gain:         #22d3a0   (CSS class: text-gain / bg-gain, var --gain)
Loss:         #f87171   (CSS class: text-loss / bg-loss, var --loss)
Warning:      #fbbf24   (CSS class: text-warning / bg-warning, var --warning)
Sidebar width: 54px (CSS var --sw)
Chat panel:   280px default, 240px min, 520px max (CSS var --cp)
```

**Prototype section anchors for continuity** (reference by element ID in `prototype-ui.html`):
- `#chatPanel` — AI chat panel (A6)
- `#cpResize` — drag handle (A6)
- `#chatToggle` — topbar toggle button (A5)
- `#portfolioDrawer` — bottom drawer (N2)
- `#drawerBackdrop` — drawer overlay (N2)
- `.sb` — sidebar (A4)
- `.tiles` — overview stat tiles row (N1)
- `.wl-grid` — watchlist 4-col grid (B3)
- `.idx-grid` — market indexes 3-col grid (B2)

---

## Phase A — Shell

### A1. Design Tokens (`globals.css`)

Replace the entire current shadcn OKLCH palette. This app is **dark-mode only** — no `.dark` class block is needed.

**`next-themes` handling:** Change `ThemeProvider` in `app/providers.tsx` from `defaultTheme="system" enableSystem` to `defaultTheme="dark"` with `forcedTheme="dark"` and remove `enableSystem`. Update `Toaster` in `components/ui/sonner.tsx` to always use `theme="dark"`. This prevents OS light-mode from conflicting with the fixed dark palette.

**`globals.css` `:root` block — complete token set:**

```css
:root {
  /* Surfaces */
  --background: #070d18;
  --card: #0b1525;
  --card2: #0f1d32;
  --hov: #121f33;

  /* Borders */
  --border: rgba(255, 255, 255, 0.07);
  --bhi: rgba(56, 189, 248, 0.22);
  --input: rgba(255, 255, 255, 0.07);
  --ring: rgba(56, 189, 248, 0.4);

  /* Text */
  --foreground: #e8f0ff;
  --muted-foreground: #6a80a8;
  --subtle: #2d3e5a;

  /* Accent */
  --cyan: #38bdf8;
  --cdim: rgba(56, 189, 248, 0.12);
  --cg: rgba(56, 189, 248, 0.35);
  --primary: #38bdf8;
  --primary-foreground: #070d18;

  /* Semantic */
  --gain: #22d3a0;
  --gdim: rgba(34, 211, 160, 0.11);
  --loss: #f87171;
  --ldim: rgba(248, 113, 113, 0.11);
  --warning: #fbbf24;
  --wdim: rgba(251, 191, 36, 0.09);
  --warning-foreground: #070d18;
  --destructive: #f87171;

  /* Secondary / Muted surfaces */
  --secondary: #0f1d32;
  --secondary-foreground: #e8f0ff;
  --muted: #0b1525;
  --accent: #121f33;
  --accent-foreground: #e8f0ff;
  --popover: #0b1525;
  --popover-foreground: #e8f0ff;

  /* Layout */
  --sw: 54px;   /* sidebar width */
  --cp: 280px;  /* chat panel width (updated dynamically via JS) */
  --radius: 0.625rem;
}
```

**`@theme inline` block additions** (exposes tokens as Tailwind utility classes):

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card2: var(--card2);
  --color-hov: var(--hov);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-subtle: var(--subtle);
  --color-cyan: var(--cyan);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-gain: var(--gain);
  --color-loss: var(--loss);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-destructive: var(--destructive);
  --font-sans: var(--font-sora);
  --font-mono: var(--font-jetbrains-mono);
}
```

This generates Tailwind utilities: `bg-card2`, `bg-hov`, `text-subtle`, `text-cyan`, `bg-gain`, `text-gain`, `bg-loss`, `text-loss`, `text-warning`, `bg-warning`, etc.

Tokens used only via raw CSS vars (not Tailwind classes): `--cdim`, `--gdim`, `--ldim`, `--wdim`, `--bhi`, `--cg`, `--sw`, `--cp`. These are layout/opacity variants used inline.

**`design-tokens.ts` update:** Add `--cyan`, `--warning`, `--subtle`, `--card2`, `--hov`, `--bhi` to the `CSS_VARS` export so chart components and `readCssVar()` can reference them by name. The existing `--gain`, `--loss`, `--neutral-signal`, `--chart-price`, etc. remain unchanged.

### A2. Typography (`app/layout.tsx`)

Load via `next/font/google`:

```tsx
import { Sora, JetBrains_Mono } from "next/font/google";

const sora = Sora({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sora",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains-mono",
});
```

Apply both `variable` classes to `<html>`: `className={cn(sora.variable, jetbrainsMono.variable)}`.

Usage rule: all numeric displays (prices, scores, P&L, percentages, counts) use `font-mono`. All labels, headings, nav, descriptions use default `font-sans`.

### A3. Authenticated Layout (`app/(authenticated)/layout.tsx`)

This becomes a **client component** because it manages the `chatIsOpen` state needed by both the topbar toggle and the chat panel and portfolio drawer.

Current structure:
```tsx
// Server component — no state
<div className="min-h-screen">
  <NavBar />
  <main className="mx-auto max-w-7xl px-4 py-6 animate-fade-in">
    {children}
  </main>
</div>
```

New structure:
```tsx
"use client";
// Full-height flex shell — no max-width constraint at layout level
// Individual pages handle their own max-width/padding
<div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
  <SidebarNav />
  <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
    <Topbar chatIsOpen={chatIsOpen} onToggleChat={() => setChatIsOpen(v => !v)} />
    <main style={{ flex: 1, overflowY: "auto" }}>
      <div className="px-4 py-6 animate-fade-in">
        {children}
      </div>
    </main>
  </div>
  <ChatPanel isOpen={chatIsOpen} onClose={() => setChatIsOpen(false)} />
</div>
```

**Important:** Remove `max-w-7xl mx-auto` from layout — pages like the screener benefit from full width. Each page adds its own container constraints if needed.

`ChatPanel` is mounted at layout level so it persists conversation state across page navigations without remounting.

### A4. Sidebar (`components/sidebar-nav.tsx`)

**Replaces:** `nav-bar.tsx`. After `sidebar-nav.tsx` is created and `layout.tsx` is updated, confirm zero remaining imports of `nav-bar.tsx` (`grep -r "nav-bar" frontend/src`), then delete the file.

**Structure:**
- `"use client"` — needs `usePathname()`
- 54px fixed width (`width: var(--sw)`), full height, `background: var(--card)`, right border `var(--border)`
- Top: StockSignal logo mark — "S" in cyan rounded square with glow (`box-shadow: 0 0 18px var(--cg)`)
- Middle `<nav>`: 3 nav items (Dashboard, Screener, Portfolio)
- Bottom: Settings icon + user avatar (see logout spec below)
- Each nav item: `<Link>` wrapping a 32px icon container, 40px tall, icon centered
- Active state: `color: var(--cyan)` + left border indicator (2px wide, 20px tall, `background: var(--cyan)`, `box-shadow: 0 0 8px var(--cg)`, `border-radius: 0 2px 2px 0`)
- Inactive: `color: var(--subtle)`, hover: `color: var(--muted-foreground)`, hover background on icon container: `var(--hov)`

**Nav items:**
```tsx
const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener",  label: "Screener",  icon: SlidersHorizontal },
  { href: "/portfolio", label: "Portfolio",  icon: PieChart },
] as const;
```

**Tooltip:** CSS-only via Tailwind group/peer pattern or a simple `<span>` with absolute positioning. Appears to the right: `left: calc(100% + 8px)`, `top: 50%`, `transform: translateY(-50%)`. Visible on `:hover` of the nav item. Background `var(--card2)`, border `var(--border)`, `font-size: 11px`, `white-space: nowrap`. Add `aria-label={item.label}` to each `<Link>` for accessibility.

**Logout affordance:** User avatar at the bottom opens a small Radix `<Popover>` containing a single "Logout" button that calls `useAuth().logout()`. The avatar is a 26px circle with initials, gradient background (`linear-gradient(135deg, #38bdf8, #6366f1)`). No `/settings` page exists — the Settings icon is rendered as a visual placeholder only (no `onClick` / `href`) until a settings page is built in a future phase.

### A5. Topbar (`components/topbar.tsx`)

Extracted as a separate client component (not inline in layout) for cleanliness.

```tsx
interface TopbarProps {
  chatIsOpen: boolean;
  onToggleChat: () => void;
}
```

**Layout:** 46px height, `background: var(--background)`, bottom border `var(--border)`, `display: flex; align-items: center; justify-content: space-between; padding: 0 18px`.

**Left:** Breadcrumb — `"StockSignal"` in `text-subtle` / page name in `text-foreground font-semibold`. Page name derived from `usePathname()`.

**Center:** `<TickerSearch />` (existing component, restyled to dark tokens). No logic changes.

**Right side chips and button:**

- **Market status chip:** Derived client-side from current time in NYSE timezone (America/New_York). Market is open Mon–Fri 09:30–16:00 ET. No backend call needed. Shows green dot + "Market Open" or dim dot + "Market Closed". Logic: `const isOpen = isNYSEOpen(new Date())` — implement as a pure utility function `lib/market-hours.ts`.

- **Signal count chip:** Derived from `useWatchlist()` data (already fetched on dashboard). Count of watchlist items where `composite_score >= 0.6` (BUY threshold). Shows `"{n} signals"`. If not on dashboard, this hook is re-fetched (TanStack Query deduplicates). Keep this chip simple — it is informational only.

- **AI Analyst toggle button:** Cyan-tinted border + text when inactive; solid cyan background + dark text when active (`chatIsOpen === true`). Calls `onToggleChat`.

### A6. Chat Panel (`components/chat-panel.tsx`)

**Default state:** Open on first load. Width persisted in `localStorage` under key `"stocksignal:cp-width"` (namespaced to avoid collisions — see localStorage key registry in A7).

**Props:**
```tsx
interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
}
```

**Structure:**
```tsx
<aside
  style={{
    width: "var(--cp)",
    minWidth: "var(--cp)",
    transform: isOpen ? "translateX(0)" : "translateX(100%)",
    transition: "transform 0.25s cubic-bezier(.22,.68,0,1.1)",
    // other styles...
  }}
>
  <div id="cpResize" />    {/* 5px drag handle, position: absolute, left: 0, top: 0, bottom: 0 */}
  <header>...</header>
  <div className="messages">...</div>
  <div className="suggestions">...</div>
  <footer>...</footer>
</aside>
```

**`--cp` lifecycle — critical detail:**
- On mount: read `localStorage.getItem("stocksignal:cp-width") ?? "280"`, set `document.documentElement.style.setProperty("--cp", width + "px")`
- On drag: update `--cp` in real time via `document.documentElement.style.setProperty`
- On drag end: persist to `localStorage`
- On close (panel hides): do NOT change `--cp` value — the panel uses `transform: translateX(100%)` to hide, so `--cp` retaining its value is fine. The `PortfolioDrawer`'s `right` is controlled by React state (`chatIsOpen`), not the CSS var, so there is no layout gap issue: `right: chatIsOpen ? "var(--cp)" : 0`.

**Resize logic:**
```tsx
// In useEffect on mount:
handle.addEventListener("mousedown", (e) => {
  e.preventDefault();
  const startX = e.clientX;
  const startWidth = aside.offsetWidth;
  document.body.classList.add("resizing"); // user-select:none; cursor:col-resize

  const onMove = (e: MouseEvent) => {
    const delta = startX - e.clientX; // drag left = wider
    const newWidth = Math.min(520, Math.max(240, startWidth + delta));
    document.documentElement.style.setProperty("--cp", newWidth + "px");
  };
  const onUp = () => {
    document.body.classList.remove("resizing");
    localStorage.setItem("stocksignal:cp-width",
      document.documentElement.style.getPropertyValue("--cp").replace("px", ""));
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  };
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
});
```

**Phase 4 integration point:**
- `useChatSession` hook is stubbed: returns `{ messages: [], sendMessage: async () => {} }`
- The full hook implementation (streaming NDJSON, session persistence) is built in the Phase 4 backend spec
- Suggested prompt pills are hardcoded for now: "Analyze my portfolio", "Best signals today", "What's happening with NVDA?"

**Content (stub state):**
- Render a single bot greeting message: "Hi! I'm your AI analyst. Ask me anything about your portfolio or watchlist."
- Input textarea + send button (disabled, shows tooltip "Coming soon" until Phase 4 wires the backend)

### A7. localStorage Key Registry

To prevent future key collisions, all `localStorage` keys used in this app are namespaced with `"stocksignal:"`:

| Key | Component | Value |
|-----|-----------|-------|
| `stocksignal:cp-width` | `chat-panel.tsx` | Chat panel pixel width (number as string) |
| `stocksignal:density` | `density-context.tsx` | `"comfortable"` \| `"compact"` |

Add a `lib/storage-keys.ts` constants file:
```ts
export const STORAGE_KEYS = {
  CHAT_PANEL_WIDTH: "stocksignal:cp-width",
  SCREENER_DENSITY: "stocksignal:density",
} as const;
```

Update `density-context.tsx` to use `STORAGE_KEYS.SCREENER_DENSITY` instead of its current hardcoded key.

---

## Phase B — Component Restyling

### Approach

All component logic is **unchanged**. Only className strings and inline style values are updated to use new design tokens. No props are added or removed unless explicitly specified. No behaviour changes.

The `cn()` utility and Tailwind classes are the primary mechanism. Raw CSS vars (`var(--bhi)`, `var(--cdim)`, etc.) are used inline where Tailwind utilities don't map cleanly.

### B1. Sparkline (`components/sparkline.tsx`)

**Current API:**
```tsx
interface SparklineProps {
  data: number[];
  sentiment?: "bullish" | "bearish" | "neutral";
  width?: number;
  height?: number;
}
```

**New API:**
```tsx
interface SparklineProps {
  data: number[];
  volumes?: number[];        // NEW optional — renders volume bars if provided
  color?: string;            // NEW optional — explicit color string
  sentiment?: "bullish" | "bearish" | "neutral";  // KEPT for backward compat
  width?: number;
  height?: number;
}
```

`sentiment` is **kept** for backward compatibility — all existing call sites continue to work unchanged. `color` overrides `sentiment` if both are provided. Color resolution: if `color` provided, use it; else resolve from `sentiment` via `readCssVar` as today.

**Implementation change:** Replace the Recharts `LineChart` SVG path with a raw `<svg>` using `<polyline>` for the price line and `<rect>` elements for volume bars. Since the app is now dark-only, the `MutationObserver` in `useSparklineColor` can be removed — replace it with a simple `useState(() => resolveColor(sentiment))` with no observer. The color is resolved once on mount and never changes (no theme toggling).

**Volume bars:** Render in bottom 20% of the viewBox height. Each bar: `opacity={0.35}`, same color as the price line. Bar width: `viewBox.width / data.length * 0.7` (70% of slot width). Normalize bar heights relative to `Math.max(...volumes)`.

**Call sites using `sentiment` prop** (no changes needed at call sites):
- `index-card.tsx`
- `stock-card.tsx`
- `screener-grid.tsx`

### B2. Index Card (`components/index-card.tsx`)

- Container: `bg-card border border-[var(--border)] rounded-[var(--radius)] overflow-hidden relative`
- Top accent line: `::after` pseudo or `<div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-cyan to-transparent" />`
- Index name label: `text-[10px] font-semibold uppercase tracking-[0.07em] text-muted-foreground`
- Value: `font-mono text-[17px] font-semibold tracking-tight`
- Change: `font-mono text-[11px] font-semibold` in `text-gain` or `text-loss`
- Sparkline: `<Sparkline sentiment={isPositive ? "bullish" : "bearish"} />`

### B3. Stock Card (`components/stock-card.tsx`)

- Container: `bg-card border border-[var(--border)] rounded-[var(--radius)] cursor-pointer transition-colors hover:bg-hov hover:border-[var(--bhi)]`
- Ticker: `font-mono text-[14px] font-semibold text-foreground`
- Company name: `text-[10px] text-subtle mt-0.5`
- Price: `font-mono text-[14px] font-semibold text-foreground text-right`
- Change %: `font-mono text-[11px]` in `text-gain` or `text-loss`
- Signal badge: see B6
- Score bar: `h-[3px] rounded-full bg-[var(--cdim)]` with fill in `bg-cyan` / `bg-gain` / `bg-loss`
- Sparkline: `<Sparkline sentiment={...} volumes={item.volumes} />`

### B4. Section Heading (`components/section-heading.tsx`)

- Label text: `text-[9.5px] font-semibold uppercase tracking-[0.1em] text-subtle`
- Bottom margin: `mb-[7px]`
- Right action slot: unchanged

### B5. Metric Card (`components/metric-card.tsx`)

- Container: `bg-card2 border border-[var(--border)] rounded-[var(--radius)] p-[10px_13px]`
- Label: `text-[9px] uppercase tracking-[0.08em] text-subtle mb-1`
- Value: `font-mono text-[16px] font-semibold text-foreground`

### B6. Signal Badge + Score Badge

```tsx
// BUY
"bg-[var(--gdim)] text-gain border border-[rgba(34,211,160,.2)] font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] rounded-full px-2 py-0.5"

// HOLD
"bg-[var(--wdim)] text-warning border border-[rgba(251,191,36,.18)] font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] rounded-full px-2 py-0.5"

// SELL
"bg-[var(--ldim)] text-loss border border-[rgba(248,113,113,.2)] font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] rounded-full px-2 py-0.5"
```

### B7. Empty State + Error State

- Icon: `text-subtle`
- Title: `text-foreground`
- Description: `text-muted-foreground`
- Container: transparent background

### B8. Change Indicator

- Positive: `text-gain font-mono`
- Negative: `text-loss font-mono`
- Neutral/zero: `text-subtle font-mono`
- Arrow icons: `text-gain` / `text-loss`

### B9. Screener Components

- `screener-table.tsx`: table border `border-[var(--border)]`, row hover `bg-hov`, header `text-subtle uppercase text-[9.5px] tracking-[0.1em]`
- `screener-grid.tsx`: cards use stock-card restyling
- `screener-filters.tsx`: filter chips `bg-card2 border-[var(--border)]`, active chip `border-[var(--bhi)] text-cyan`

### B10. Stock Detail Components

- All card surfaces: `bg-card` / `bg-card2`
- `price-chart.tsx`, `signal-history-chart.tsx`, `portfolio-value-chart.tsx`: chart colors already via `useChartColors()` — no logic change, only ensure `design-tokens.ts` has new token names registered
- `stock-header.tsx`: ticker `font-mono text-2xl font-bold`, price `font-mono`, change `text-gain`/`text-loss`
- `signal-cards.tsx`, `fundamentals-card.tsx`, `dividend-card.tsx`, `risk-return-card.tsx`: surface + typography token updates

### B11. Portfolio Components

- `rebalancing-panel.tsx`, `portfolio-settings-sheet.tsx`, `log-transaction-dialog.tsx`: sheet/dialog `bg-card`, inputs `bg-card2 border-[var(--border)]`
- `ticker-search.tsx`: input `bg-card border-[var(--border)]`, results popover `bg-card2`
- `sector-filter.tsx`, `pagination-controls.tsx`: token updates

---

## New Components

### N1. Stat Tile (`components/stat-tile.tsx`)

Used in Dashboard Overview row (5 tiles). This is a purely presentational component.

```tsx
interface StatTileProps {
  label: string;
  value?: string;            // not required — children can provide content instead
  sub?: React.ReactNode;     // below value: change indicator, meta text
  onClick?: () => void;
  accentColor?: "cyan" | "gain" | "loss" | "warn";
  children?: React.ReactNode; // replaces value+sub for custom content (signals 3-cell, donut)
  className?: string;
}
```

- Container: `bg-card border border-[var(--border)] rounded-[var(--radius)] p-[13px_14px] cursor-pointer transition-colors hover:border-[var(--bhi)]`
- Top accent: 1px gradient line from `accentColor` token to transparent
- Label: `text-[9.5px] font-medium uppercase tracking-[0.09em] text-subtle mb-[5px]`
- Value: `font-mono text-[20px] font-bold tracking-tight leading-none`
- Sub: small row below value

**No tests required** for this component — it is purely presentational with no logic. Standard snapshot or visual test is sufficient.

### N2. Portfolio Drawer (`components/portfolio-drawer.tsx`)

```tsx
interface PortfolioDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  chatIsOpen: boolean;  // controls right offset to avoid overlapping chat panel
}
```

**Drawer positioning:**
```tsx
// right offset: when chat is open, drawer stops at the chat panel edge
style={{
  position: "fixed",
  left: "var(--sw)",
  right: chatIsOpen ? "var(--cp)" : 0,
  bottom: 0,
  height: isOpen ? "62vh" : 0,
  overflow: isOpen ? "auto" : "hidden",
  transition: "height 0.3s cubic-bezier(.22,.68,0,1.1), right 0.25s cubic-bezier(.22,.68,0,1.1)",
  background: "var(--card)",
  borderTop: "1px solid var(--bhi)",
  borderRadius: "14px 14px 0 0",
  zIndex: 50,
  boxShadow: "0 -20px 60px rgba(56,189,248,.08)",
}}
```

**Backdrop:**
```tsx
// Shown when isOpen — separate div, zIndex: 40, below drawer
style={{
  display: isOpen ? "block" : "none",
  position: "fixed",
  inset: 0,
  background: "rgba(7,13,24,.7)",
  backdropFilter: "blur(3px)",
  zIndex: 40,
}}
```

**Contents:**
- Drag handle (36×4px rounded bar, `background: var(--border)`) — clicking calls `onClose`
- Close button (X, top-right absolute)
- Large portfolio value (`font-mono text-[30px] font-bold`)
- Full-width `<PortfolioValueChart />` (existing component)
- Stats row: 4-column grid of `<MetricCard />` with Total Gain, Today's Change, Allocation count, Portfolio Beta (or similar from existing data)

**Data:** Uses `usePortfolioSummary()` — extracted and exported from `hooks/use-stocks.ts` (see Dashboard data sources below).

### N3. Allocation Donut (`components/allocation-donut.tsx`)

```tsx
interface AllocationDonutProps {
  allocations: { sector: string; pct: number; color: string }[];
  stockCount?: number;  // shown in centre hole
}
```

**CSS conic-gradient computation:**
```tsx
// Build gradient string from allocations
function buildGradient(allocations: { pct: number; color: string }[]) {
  let cumulative = 0;
  const stops = allocations.map(({ pct, color }) => {
    const start = cumulative;
    cumulative += pct;
    return `${color} ${start}% ${cumulative}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}
```

- Donut: 72×72px circle, `background: {gradient}`, flex-shrink: 0
- Hole: 46×46px circle, `background: var(--card)`, centred inside, shows `stockCount` + "stocks" in `text-[9px] text-muted-foreground text-center`
- Legend: flex column, 3 items max shown ("+N more" if > 3 sectors)
- Sector colors: use a fixed palette of 6 colors cycling: `[var(--cyan), var(--warning), #a78bfa, var(--gain), var(--loss), #fb923c]`
- Empty state: if `allocations.length === 0`, show "No positions" in `text-subtle`

---

## Dashboard Page Updates (`app/(authenticated)/dashboard/page.tsx`)

New layout:
```
Market Indexes (3-col grid)
Overview (5-col grid):
  [Portfolio Value] [Unrealized P&L] [Signals 3-cell] [Top Signal] [Allocation]
Watchlist (4-col grid)
```

**Data sources — corrected:**

`usePortfolioSummary` and `usePositions` are currently **private functions** inside `portfolio-client.tsx`. They must be extracted and exported from `hooks/use-stocks.ts` as public hooks before the dashboard can use them.

Steps:
1. Move `usePortfolioSummary` from `portfolio-client.tsx` to `hooks/use-stocks.ts` and export it
2. Move `usePositions` from `portfolio-client.tsx` to `hooks/use-stocks.ts` and export it
3. Update `portfolio-client.tsx` to import them from `hooks/use-stocks.ts`
4. In `dashboard/page.tsx`, import and use them directly

`usePortfolioAllocations` does not exist. Derive allocation data inline in the dashboard from `usePositions()`:
```tsx
const allocations = useMemo(() => {
  if (!positions) return [];
  const sectorTotals: Record<string, number> = {};
  let total = 0;
  positions.forEach(p => {
    const sector = p.sector ?? "Other";
    sectorTotals[sector] = (sectorTotals[sector] ?? 0) + p.market_value;
    total += p.market_value;
  });
  return Object.entries(sectorTotals).map(([sector, value], i) => ({
    sector,
    pct: total > 0 ? (value / total) * 100 : 0,
    color: DONUT_COLORS[i % DONUT_COLORS.length],
  }));
}, [positions]);
```

**Signals tile data:**
```tsx
const signalCounts = useMemo(() => {
  if (!watchlist) return { buy: 0, hold: 0, sell: 0 };
  return watchlist.reduce((acc, w) => {
    if (w.composite_score >= 0.6) acc.buy++;
    else if (w.composite_score >= 0.4) acc.hold++;
    else acc.sell++;
    return acc;
  }, { buy: 0, hold: 0, sell: 0 });
}, [watchlist]);
```

**Top Signal tile:** Highest `composite_score` item from watchlist where score >= 0.6. Show ticker + score + BUY badge + mini sparkline.

**Portfolio Value tile onClick:** `setDrawerOpen(true)` — opens `<PortfolioDrawer />`.

---

## Testing

Per CLAUDE.md policy, all new components need tests. Existing restyled components only need tests if the **logic** changes (it doesn't in Phase B, so no new tests are required for restyled components).

New components that need tests:
- `stat-tile.tsx` — render test: renders label, value, children
- `allocation-donut.tsx` — unit test: `buildGradient()` function, empty state render
- `portfolio-drawer.tsx` — render test: open/closed state, chatIsOpen offset
- `chat-panel.tsx` — render test: open/closed state, resize handle exists
- `sidebar-nav.tsx` — render test: active link detection, logout popover
- `lib/market-hours.ts` — unit tests with `freezegun`-equivalent (mock `Date`): market open on weekday 10am ET, closed on weekend, closed before 9:30, closed after 16:00

---

## Component Inventory — No Tech Debt Policy

Every existing component is accounted for:

| Component | Action |
|-----------|--------|
| `nav-bar.tsx` | **Delete** — replaced by `sidebar-nav.tsx` |
| `index-card.tsx` | Restyle (Phase B) |
| `stock-card.tsx` | Restyle (Phase B) |
| `sparkline.tsx` | Restyle + volumes prop, drop MutationObserver (Phase B) |
| `section-heading.tsx` | Restyle (Phase B) |
| `score-badge.tsx` | Restyle (Phase B) |
| `signal-badge.tsx` | Restyle (Phase B) |
| `signal-meter.tsx` | Token update (Phase B) |
| `metric-card.tsx` | Token update (Phase B) |
| `change-indicator.tsx` | Token update (Phase B) |
| `chart-tooltip.tsx` | Token update (Phase B) |
| `empty-state.tsx` | Token update (Phase B) |
| `error-state.tsx` | Token update (Phase B) |
| `breadcrumbs.tsx` | Token update (Phase B) |
| `screener-filters.tsx` | Token update (Phase B) |
| `screener-grid.tsx` | Token update (Phase B) |
| `screener-table.tsx` | Token update (Phase B) |
| `stock-header.tsx` | Token update (Phase B) |
| `signal-cards.tsx` | Token update (Phase B) |
| `signal-history-chart.tsx` | Token update (Phase B) |
| `fundamentals-card.tsx` | Token update (Phase B) |
| `dividend-card.tsx` | Token update (Phase B) |
| `risk-return-card.tsx` | Token update (Phase B) |
| `portfolio-value-chart.tsx` | Token update (Phase B) |
| `price-chart.tsx` | Token update (Phase B) |
| `rebalancing-panel.tsx` | Token update (Phase B) |
| `portfolio-settings-sheet.tsx` | Token update (Phase B) |
| `log-transaction-dialog.tsx` | Token update (Phase B) |
| `ticker-search.tsx` | Token update (Phase B) |
| `sector-filter.tsx` | Token update (Phase B) |
| `pagination-controls.tsx` | Token update (Phase B) |
| `relative-time.tsx` | Token update (Phase B) |
| All `components/ui/*` | **Untouched** (shadcn primitives) |
| `lib/density-context.tsx` | Update to use `STORAGE_KEYS.SCREENER_DENSITY` |

---

## Implementation Order

### Phase A — Shell (do first, unblocks everything)
1. `lib/storage-keys.ts` — localStorage key registry constant file
2. `lib/market-hours.ts` — NYSE hours utility + tests
3. `globals.css` — full token replacement, dark-only, `@theme inline` additions
4. `lib/design-tokens.ts` — add new token names (`--cyan`, `--warning`, `--subtle`, `--card2`, `--hov`, `--bhi`)
5. `app/layout.tsx` — Sora + JetBrains Mono fonts
6. `app/providers.tsx` — `ThemeProvider` force dark (`defaultTheme="dark" forcedTheme="dark"`, remove `enableSystem`)
7. `components/ui/sonner.tsx` — `Toaster theme="dark"` hardcoded
8. `hooks/use-stocks.ts` — extract + export `usePortfolioSummary` and `usePositions`
9. `app/(authenticated)/portfolio/portfolio-client.tsx` — update imports
10. `components/sidebar-nav.tsx` — new icon sidebar with logout popover
11. `components/topbar.tsx` — new topbar component
12. `components/chat-panel.tsx` — docked resizable panel (stubbed AI)
13. `app/(authenticated)/layout.tsx` — new flex shell using above components
14. `lib/density-context.tsx` — update to use `STORAGE_KEYS.SCREENER_DENSITY`
15. Verify `grep -r "nav-bar" frontend/src` returns nothing → delete `nav-bar.tsx`

### Phase B — Components (page by page)
16. `components/sparkline.tsx` — polyline + volumes, drop MutationObserver
17. `components/index-card.tsx` — restyle
18. `components/stock-card.tsx` — restyle
19. `components/section-heading.tsx`, `signal-badge.tsx`, `score-badge.tsx` — shared atoms
20. `components/change-indicator.tsx`, `metric-card.tsx`, `chart-tooltip.tsx` — atoms
21. `components/stat-tile.tsx` — new component
22. `components/allocation-donut.tsx` — new component
23. `components/portfolio-drawer.tsx` — new component
24. `app/(authenticated)/dashboard/page.tsx` — wire Overview tiles row + portfolio drawer
25. Stock detail components: `stock-header.tsx`, `signal-cards.tsx`, `signal-history-chart.tsx`, `price-chart.tsx`, `fundamentals-card.tsx`, `dividend-card.tsx`, `risk-return-card.tsx`
26. Portfolio components: `portfolio-value-chart.tsx`, `rebalancing-panel.tsx`, `portfolio-settings-sheet.tsx`, `log-transaction-dialog.tsx`
27. Screener components: `screener-filters.tsx`, `screener-grid.tsx`, `screener-table.tsx`
28. Remaining: `ticker-search.tsx`, `sector-filter.tsx`, `pagination-controls.tsx`, `relative-time.tsx`, `signal-meter.tsx`, `empty-state.tsx`, `error-state.tsx`, `breadcrumbs.tsx`

---

## What This Spec Does NOT Cover

- Phase 4 AI backend (LangGraph agents, streaming router, ChatSession model) — separate spec
- Drag-to-reorder watchlist (dnd-kit) — Phase 5
- Candlestick / zoom chart views — Phase 5
- Mobile responsiveness — future phase
- `/settings` page — future phase (Settings icon in sidebar is visual placeholder only)

---

## Continuity Notes

If context runs out mid-implementation, resume by:
1. Reading this spec — `docs/superpowers/specs/2026-03-15-ui-redesign-phase-4-shell-design.md`
2. Reading the implementation plan — `docs/superpowers/plans/ui-redesign-implementation.md`
3. Checking `PROGRESS.md` for last completed step
4. Running `cd frontend && npm run dev` and visually comparing against `prototype-ui.html` (open in browser alongside)
5. The Implementation Order list above is numbered — find the last completed step number in PROGRESS.md and resume from the next one

**Visual ground truth:** `prototype-ui.html` (project root). Key element IDs for reference:
- `#chatPanel` / `#cpResize` — chat panel and drag handle
- `#chatToggle` — topbar AI Analyst button
- `#portfolioDrawer` / `#drawerBackdrop` — bottom drawer
- `.sb` — sidebar, `.tiles` — overview row, `.wl-grid` — watchlist, `.idx-grid` — indexes
