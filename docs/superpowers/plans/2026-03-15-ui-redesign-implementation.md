# UI Redesign + Phase 4 Shell Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the top-navbar light-mode UI with a command-center dark theme — navy palette, icon sidebar, resizable AI chat panel — while restyling all existing components to match.

**Architecture:** Phase A establishes the design token foundation and shell layout (sidebar + chat panel) that all pages share. Phase B restyls existing components page-by-page using the new tokens. No backend changes are needed — the chat panel is wired with a UI stub for now; Phase 4 backend spec handles the AI integration.

**Tech Stack:** Next.js App Router, TypeScript, Tailwind CSS v4, shadcn/ui, lucide-react, next/font/google, Radix UI Popover

**Test framework:** This project does NOT use Vitest. Check with `cat frontend/package.json | grep -E "jest|vitest"` before writing tests. Use `jest.fn()` and `.toHaveBeenCalledTimes(1)` (Jest), NOT `vi.fn()` or `toHaveBeenCalledOnce()` (Vitest).

**Spec:** `docs/superpowers/specs/2026-03-15-ui-redesign-phase-4-shell-design.md`
**Visual reference:** `prototype-ui.html` (project root — open in browser alongside dev server)

---

## Chunk 1: Foundations (Tokens, Fonts, Providers)

### Task 1: localStorage Key Registry

**Files:**
- Create: `frontend/src/lib/storage-keys.ts`
- Modify: `frontend/src/lib/density-context.tsx`

- [ ] **Create `frontend/src/lib/storage-keys.ts`:**

```typescript
// Centralised localStorage key registry — all keys namespaced with "stocksignal:"
// to prevent collisions with browser extensions and future features.
export const STORAGE_KEYS = {
  CHAT_PANEL_WIDTH: "stocksignal:cp-width",
  SCREENER_DENSITY: "stocksignal:density",
} as const;
```

- [ ] **Update `frontend/src/lib/density-context.tsx` to use the registry.**

At the top of the file, add the import after existing imports:
```typescript
import { STORAGE_KEYS } from "@/lib/storage-keys";
```

Then find and **replace** the entire constant line (line 20):
```typescript
// Remove this line entirely:
const STORAGE_KEY = "screener-density";
```
And wherever `STORAGE_KEY` is used, replace with `STORAGE_KEYS.SCREENER_DENSITY` directly (two occurrences: `localStorage.getItem` and `localStorage.setItem`).

Note: existing users lose their stored density preference on first load (one-time reset — acceptable). Add a comment in the commit message noting this migration.

- [ ] **Commit:**
```bash
git add frontend/src/lib/storage-keys.ts frontend/src/lib/density-context.tsx
git commit -m "feat: add localStorage key registry, migrate density-context key"
```

---

### Task 2: Market Hours Utility

**Files:**
- Create: `frontend/src/lib/market-hours.ts`
- Create: `frontend/src/lib/__tests__/market-hours.test.ts`

- [ ] **Write the failing tests first:**

```typescript
// frontend/src/lib/__tests__/market-hours.test.ts
import { isNYSEOpen } from "../market-hours";

describe("isNYSEOpen", () => {
  // NYSE hours: Mon-Fri 09:30–16:00 America/New_York

  it("returns true on a weekday at 10am ET", () => {
    // 2026-03-16 Monday 10:00 ET = 15:00 UTC
    const date = new Date("2026-03-16T15:00:00Z");
    expect(isNYSEOpen(date)).toBe(true);
  });

  it("returns false before 09:30 ET on a weekday", () => {
    // 2026-03-16 Monday 09:00 ET = 14:00 UTC
    const date = new Date("2026-03-16T14:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns false after 16:00 ET on a weekday", () => {
    // 2026-03-16 Monday 16:30 ET = 21:30 UTC
    const date = new Date("2026-03-16T21:30:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns false on Saturday", () => {
    // 2026-03-21 Saturday 12:00 ET = 17:00 UTC
    const date = new Date("2026-03-21T17:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns false on Sunday", () => {
    const date = new Date("2026-03-22T17:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });

  it("returns true exactly at 09:30 ET", () => {
    // 2026-03-16 09:30 EDT = 13:30 UTC (EDT is UTC-4, in effect after Mar 8 DST change)
    const date = new Date("2026-03-16T13:30:00Z");
    expect(isNYSEOpen(date)).toBe(true);
  });

  it("returns false exactly at 16:00 ET (market closed)", () => {
    const date = new Date("2026-03-16T20:00:00Z");
    expect(isNYSEOpen(date)).toBe(false);
  });
});
```

- [ ] **Run tests to confirm they fail:**
```bash
cd frontend && npx jest src/lib/__tests__/market-hours.test.ts
```
Expected: `Cannot find module '../market-hours'`

- [ ] **Implement `frontend/src/lib/market-hours.ts`:**

```typescript
// NYSE trading hours utility — purely time-based, no API call.
// Does not account for market holidays (acceptable for status chip display).

/**
 * Returns true if NYSE is currently open based on time alone.
 * Ignores public holidays — for display purposes only.
 */
export function isNYSEOpen(date: Date = new Date()): boolean {
  // Convert to America/New_York timezone
  const nyTime = new Date(
    date.toLocaleString("en-US", { timeZone: "America/New_York" })
  );

  const day = nyTime.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;

  const hours = nyTime.getHours();
  const minutes = nyTime.getMinutes();
  const timeInMinutes = hours * 60 + minutes;

  const openTime = 9 * 60 + 30;  // 09:30
  const closeTime = 16 * 60;     // 16:00

  return timeInMinutes >= openTime && timeInMinutes < closeTime;
}
```

- [ ] **Run tests — all should pass:**
```bash
cd frontend && npx jest src/lib/__tests__/market-hours.test.ts
```
Expected: 7 tests pass.

- [ ] **Commit:**
```bash
git add frontend/src/lib/market-hours.ts frontend/src/lib/__tests__/market-hours.test.ts
git commit -m "feat: add NYSE market hours utility with tests"
```

---

### Task 3: Design Tokens (globals.css)

**Files:**
- Modify: `frontend/src/app/globals.css`

This is a complete replacement of the CSS token system. The app becomes dark-mode only.

- [ ] **Replace the entire contents of `frontend/src/app/globals.css`:**

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@custom-variant dark (&:is(.dark *));

@theme inline {
  /* Core surfaces */
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card2: var(--card2);
  --color-hov: var(--hov);
  --color-card-foreground: var(--card-foreground);

  /* Borders & inputs */
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);

  /* Text hierarchy */
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-subtle: var(--subtle);

  /* Accent */
  --color-cyan: var(--cyan);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);

  /* Secondary */
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);

  /* Semantic financial */
  --color-gain: var(--gain);
  --color-gain-foreground: var(--gain-foreground);
  --color-loss: var(--loss);
  --color-loss-foreground: var(--loss-foreground);
  --color-warning: var(--warning);
  --color-warning-foreground: var(--warning-foreground);
  --color-destructive: var(--destructive);

  /* Sidebar (kept for shadcn compatibility) */
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);

  /* Typography */
  --font-sans: var(--font-sora);
  --font-mono: var(--font-jetbrains-mono);

  /* Radii */
  --radius-sm: calc(var(--radius) * 0.6);
  --radius-md: calc(var(--radius) * 0.8);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) * 1.4);
}

/* ── Dark-only navy palette ─────────────────────────────────────────────── */
:root {
  /* Surfaces */
  --background: #070d18;
  --foreground: #e8f0ff;
  --card: #0b1525;
  --card2: #0f1d32;
  --hov: #121f33;
  --card-foreground: #e8f0ff;

  /* Borders */
  --border: rgba(255, 255, 255, 0.07);
  --bhi: rgba(56, 189, 248, 0.22);
  --input: rgba(255, 255, 255, 0.07);
  --ring: rgba(56, 189, 248, 0.4);

  /* Text */
  --muted: #0b1525;
  --muted-foreground: #6a80a8;
  --subtle: #2d3e5a;

  /* Cyan accent */
  --cyan: #38bdf8;
  --cdim: rgba(56, 189, 248, 0.12);
  --cg: rgba(56, 189, 248, 0.35);
  --primary: #38bdf8;
  --primary-foreground: #070d18;

  /* Secondary / Accent surfaces */
  --secondary: #0f1d32;
  --secondary-foreground: #e8f0ff;
  --accent: #121f33;
  --accent-foreground: #e8f0ff;
  --popover: #0b1525;
  --popover-foreground: #e8f0ff;

  /* Financial semantic */
  --gain: #22d3a0;
  --gain-foreground: #070d18;
  --gdim: rgba(34, 211, 160, 0.11);
  --loss: #f87171;
  --loss-foreground: #070d18;
  --ldim: rgba(248, 113, 113, 0.11);
  --warning: #fbbf24;
  --warning-foreground: #070d18;
  --wdim: rgba(251, 191, 36, 0.09);
  --destructive: #f87171;

  /* Chart semantic */
  --chart-price: #38bdf8;
  --chart-volume: rgba(56, 189, 248, 0.35);
  --chart-sma-50: #fbbf24;
  --chart-sma-200: #a78bfa;
  --chart-rsi: #f87171;
  --chart-1: #38bdf8;
  --chart-2: #22d3a0;
  --chart-3: #a78bfa;
  --chart-4: #fbbf24;
  --chart-5: #f87171;
  --neutral-signal: #6a80a8;

  /* Sidebar (shadcn compat) */
  --sidebar: #0b1525;
  --sidebar-foreground: #e8f0ff;
  --sidebar-primary: #38bdf8;
  --sidebar-primary-foreground: #070d18;
  --sidebar-accent: #121f33;
  --sidebar-accent-foreground: #e8f0ff;
  --sidebar-border: rgba(255, 255, 255, 0.07);
  --sidebar-ring: rgba(56, 189, 248, 0.4);

  /* Layout */
  --sw: 54px;
  --cp: 280px;
  --radius: 0.625rem;
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
  html {
    @apply font-sans;
  }
}

/* ── Entry animations ───────────────────────────────────────────────────── */
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes fade-slide-up {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

@layer utilities {
  .animate-fade-in {
    animation: fade-in 0.4s ease both;
  }
  .animate-fade-slide-up {
    animation: fade-slide-up 0.4s cubic-bezier(.22,.68,0,1.2) var(--stagger-delay, 0ms) both;
  }
  /* Panel resize cursor helper */
  body.resizing {
    user-select: none;
    cursor: col-resize;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-delay: 0ms !important;
  }
}
```

- [ ] **Start dev server and verify the app renders dark:**
```bash
cd frontend && npm run dev
```
Open http://localhost:3000 — background should be `#070d18` navy-black.

- [ ] **Commit:**
```bash
git add frontend/src/app/globals.css
git commit -m "feat: replace design tokens with dark navy palette, dark-only"
```

---

### Task 4: Update design-tokens.ts

**Files:**
- Modify: `frontend/src/lib/design-tokens.ts`

⚠️ **Important:** The replacement below MUST retain all existing keys. Before replacing, run:
```bash
cat frontend/src/lib/design-tokens.ts
```
and verify that every key in the current file appears in the new version below. The new version adds keys but must not drop any existing ones (especially `chart1`, `chart2`, `chart3`, `mutedForeground`, `border`, `popover`, `popoverForeground`).

- [ ] **Replace the contents of `frontend/src/lib/design-tokens.ts`:**

```typescript
// CSS variable name constants — single source of truth for design tokens.
// Use these when accessing CSS variables programmatically (e.g., in chart themes,
// sparklines, and other components that need resolved color strings).

export const CSS_VARS = {
  // Financial semantic
  gain: "--gain",
  gainForeground: "--gain-foreground",
  loss: "--loss",
  lossForeground: "--loss-foreground",
  neutralSignal: "--neutral-signal",
  // Accent
  cyan: "--cyan",
  cdim: "--cdim",
  // Warning
  warning: "--warning",
  warningForeground: "--warning-foreground",
  // Text hierarchy
  foreground: "--foreground",
  mutedForeground: "--muted-foreground",
  subtle: "--subtle",
  // Surfaces
  card: "--card",
  card2: "--card2",
  hov: "--hov",
  // Borders
  border: "--border",
  bhi: "--bhi",
  // Chart-specific
  chartPrice: "--chart-price",
  chartVolume: "--chart-volume",
  chartSma50: "--chart-sma-50",
  chartSma200: "--chart-sma-200",
  chartRsi: "--chart-rsi",
  // shadcn chart palette
  chart1: "--chart-1",
  chart2: "--chart-2",
  chart3: "--chart-3",
  chart4: "--chart-4",
  chart5: "--chart-5",
  popover: "--popover",
  popoverForeground: "--popover-foreground",
} as const;
```

- [ ] **Commit:**
```bash
git add frontend/src/lib/design-tokens.ts
git commit -m "feat: expand design-tokens.ts with new navy palette token names"
```

---

### Task 5: Typography — Sora + JetBrains Mono

**Files:**
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Update `frontend/src/app/layout.tsx` to load fonts:**

```tsx
import type { Metadata } from "next";
import { Sora, JetBrains_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";
import { cn } from "@/lib/utils";

const sora = Sora({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sora",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "StockSignal",
  description: "Personal stock analysis and signal platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={cn(sora.variable, jetbrainsMono.variable)}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [ ] **Commit:**
```bash
git add frontend/src/app/layout.tsx
git commit -m "feat: add Sora + JetBrains Mono fonts via next/font/google"
```

---

### Task 6: Force Dark Mode in ThemeProvider

**Files:**
- Modify: `frontend/src/app/providers.tsx`
- Modify: `frontend/src/components/ui/sonner.tsx`

- [ ] **Update `ThemeProvider` in `frontend/src/app/providers.tsx`:**

Change:
```tsx
<ThemeProvider
  attribute="class"
  defaultTheme="system"
  enableSystem
  disableTransitionOnChange
>
```
To:
```tsx
<ThemeProvider
  attribute="class"
  defaultTheme="dark"
  forcedTheme="dark"
  disableTransitionOnChange
>
```

- [ ] **Update `frontend/src/components/ui/sonner.tsx`** to hardcode dark theme. Find the `<Toaster>` render and add `theme="dark"`:
```tsx
// Find the Toaster component usage and add theme prop:
<Toaster theme="dark" />
```

- [ ] **Verify in browser:** OS light mode users should still see the dark UI.

- [ ] **Commit:**
```bash
git add frontend/src/app/providers.tsx frontend/src/components/ui/sonner.tsx
git commit -m "feat: force dark mode — remove system theme toggle"
```

---

## Chunk 2: Shell Layout

### Task 7: Extract Portfolio Hooks

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts`
- Modify: `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`

These hooks are currently private in `portfolio-client.tsx`. The Dashboard page needs them.

- [ ] **Add to `frontend/src/hooks/use-stocks.ts`** — two steps:

**Step A:** At the top of the file, find the existing `import type { ... } from "@/types/api"` block (around line 6-21) and add `Position` and `PortfolioSummary` to it. Do NOT add a second import statement.

**Step B:** Append the two exported hooks after the last export in the file:

```typescript
export function usePositions() {
  return useQuery<Position[]>({
    queryKey: ["portfolio", "positions"],
    queryFn: () => get<Position[]>("/portfolio/positions"),
    staleTime: 60 * 1000,
  });
}

export function usePortfolioSummary() {
  return useQuery<PortfolioSummary>({
    queryKey: ["portfolio", "summary"],
    queryFn: () => get<PortfolioSummary>("/portfolio/summary"),
    staleTime: 60 * 1000,
  });
}

export function usePortfolioHistory(days = 365) {
  return useQuery<PortfolioSnapshot[]>({
    queryKey: ["portfolio", "history", days],
    queryFn: () => get<PortfolioSnapshot[]>(`/portfolio/history?days=${days}`),
    staleTime: 15 * 60 * 1000,
  });
}
```

Note: `get` is already imported in `use-stocks.ts`. Add `Position`, `PortfolioSummary`, and `PortfolioSnapshot` to the existing types import at the top of the file. Also extract `usePortfolioHistory` while you're here — it is needed by `PortfolioDrawer`.

- [ ] **Update `portfolio-client.tsx`** — remove the duplicate private function definitions and import from hooks:

Remove these four private functions (they're now in `use-stocks.ts`): `usePositions`, `usePortfolioSummary`, `usePortfolioHistory` (if it was already there), plus add to the import:
```typescript
import { useRebalancing, usePositions, usePortfolioSummary, usePortfolioHistory } from "@/hooks/use-stocks";
```
Also remove the private `useTransactions` and `useLogTransaction` functions only if they also exist in `use-stocks.ts` — check first with `grep "useTransactions\|useLogTransaction" frontend/src/hooks/use-stocks.ts`. If they don't exist there, leave them private in `portfolio-client.tsx`.

- [ ] **Run frontend lint to verify no type errors:**
```bash
cd frontend && npm run lint
```

- [ ] **Commit:**
```bash
git add frontend/src/hooks/use-stocks.ts frontend/src/app/\(authenticated\)/portfolio/portfolio-client.tsx
git commit -m "refactor: export usePositions + usePortfolioSummary from use-stocks"
```

---

### Task 8: Sidebar Nav

**Files:**
- Create: `frontend/src/components/sidebar-nav.tsx`

- [ ] **Create `frontend/src/components/sidebar-nav.tsx`:**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  SlidersHorizontal,
  PieChart,
  Settings,
} from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/screener",  label: "Screener",  icon: SlidersHorizontal },
  { href: "/portfolio", label: "Portfolio",  icon: PieChart },
] as const;

export function SidebarNav() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <aside
      className="flex flex-col items-center py-3.5 border-r border-border bg-card flex-shrink-0"
      style={{ width: "var(--sw)" }}
    >
      {/* Logo */}
      <div
        className="w-7 h-7 rounded-[7px] bg-cyan flex items-center justify-center mb-5 flex-shrink-0"
        style={{ boxShadow: "0 0 18px var(--cg)" }}
      >
        <span className="text-[var(--background)] font-bold text-sm leading-none flex items-center justify-center w-full h-full">
          S
        </span>
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-0.5 flex-1 w-full">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-label={item.label}
              className={cn(
                "relative w-full h-10 flex items-center justify-center group",
                isActive ? "text-cyan" : "text-subtle hover:text-muted-foreground"
              )}
            >
              {/* Active left indicator */}
              {isActive && (
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-cyan rounded-r-sm"
                  style={{ boxShadow: "0 0 8px var(--cg)" }}
                />
              )}
              {/* Icon container */}
              <span
                className={cn(
                  "w-8 h-8 rounded-[7px] flex items-center justify-center transition-colors",
                  isActive ? "bg-[var(--cdim)]" : "group-hover:bg-hov"
                )}
              >
                <Icon size={16} />
              </span>
              {/* CSS tooltip */}
              <span
                className="absolute left-[calc(100%+8px)] top-1/2 -translate-y-1/2 bg-card2 border border-border text-foreground text-[11px] px-2 py-0.5 rounded-[5px] whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50"
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom: settings placeholder + user avatar with logout */}
      <div className="flex flex-col items-center gap-0.5 w-full">
        {/* Settings — placeholder, no page yet */}
        <div className="relative w-full h-10 flex items-center justify-center group text-subtle">
          <span className="w-8 h-8 rounded-[7px] flex items-center justify-center group-hover:bg-hov transition-colors">
            <Settings size={16} />
          </span>
          <span className="absolute left-[calc(100%+8px)] top-1/2 -translate-y-1/2 bg-card2 border border-border text-foreground text-[11px] px-2 py-0.5 rounded-[5px] whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50">
            Settings (coming soon)
          </span>
        </div>

        {/* User avatar with logout popover */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              className="w-[26px] h-[26px] rounded-full flex items-center justify-center text-[10px] font-bold text-white cursor-pointer mt-1"
              style={{ background: "linear-gradient(135deg, #38bdf8, #6366f1)" }}
              aria-label="User menu"
            >
              U
            </button>
          </PopoverTrigger>
          <PopoverContent
            side="right"
            align="end"
            className="w-32 p-1 bg-card2 border-border"
          >
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start text-muted-foreground hover:text-foreground text-xs"
              onClick={logout}
            >
              Logout
            </Button>
          </PopoverContent>
        </Popover>
      </div>
    </aside>
  );
}
```

- [ ] **Run lint:**
```bash
cd frontend && npm run lint
```

- [ ] **Commit:**
```bash
git add frontend/src/components/sidebar-nav.tsx
git commit -m "feat: add SidebarNav — icon sidebar with tooltips and logout popover"
```

---

### Task 9: Topbar Component

**Files:**
- Create: `frontend/src/components/topbar.tsx`

- [ ] **Create `frontend/src/components/topbar.tsx`:**

```tsx
"use client";

import { usePathname } from "next/navigation";
import { BotIcon } from "lucide-react";
import { TickerSearch } from "@/components/ticker-search";
import { isNYSEOpen } from "@/lib/market-hours";
import { useWatchlist } from "@/hooks/use-stocks";
import { cn } from "@/lib/utils";

interface TopbarProps {
  chatIsOpen: boolean;
  onToggleChat: () => void;
  onAddTicker: (ticker: string) => void;
}

const PAGE_LABELS: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/screener": "Screener",
  "/portfolio": "Portfolio",
};

export function Topbar({ chatIsOpen, onToggleChat, onAddTicker }: TopbarProps) {
  const pathname = usePathname();
  const marketOpen = isNYSEOpen();

  const { data: watchlist } = useWatchlist();
  const signalCount =
    watchlist?.filter((w) => (w.composite_score ?? 0) >= 0.6).length ?? 0;

  // Derive page label — check exact match first, then startsWith for sub-routes
  const pageLabel =
    PAGE_LABELS[pathname] ??
    Object.entries(PAGE_LABELS).find(([k]) => pathname.startsWith(k))?.[1] ??
    "StockSignal";

  return (
    <header
      className="flex items-center justify-between flex-shrink-0 border-b border-border bg-background px-[18px]"
      style={{ height: "46px" }}
    >
      {/* Left: breadcrumb */}
      <div className="flex items-center gap-1.5 text-[11.5px]">
        <span className="text-subtle font-medium">StockSignal</span>
        <span className="text-subtle">/</span>
        <span className="text-foreground font-semibold text-[13px]">{pageLabel}</span>
      </div>

      {/* Center: search */}
      <TickerSearch onSelect={onAddTicker} />

      {/* Right: chips + AI toggle */}
      <div className="flex items-center gap-2">
        {/* Market status chip */}
        <div className="flex items-center gap-1.5 bg-card border border-border rounded-full px-2.5 py-1 text-[11px] text-muted-foreground">
          <span
            className={cn(
              "w-[5px] h-[5px] rounded-full",
              marketOpen
                ? "bg-gain shadow-[0_0_5px_var(--gain)]"
                : "bg-subtle"
            )}
          />
          {marketOpen ? "Market Open" : "Market Closed"}
        </div>

        {/* Signal count chip */}
        {signalCount > 0 && (
          <div className="flex items-center gap-1.5 bg-card border border-border rounded-full px-2.5 py-1 text-[11px] text-muted-foreground">
            <BotIcon size={11} />
            {signalCount} signal{signalCount !== 1 ? "s" : ""}
          </div>
        )}

        {/* AI Analyst toggle */}
        <button
          onClick={onToggleChat}
          className={cn(
            "flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
            chatIsOpen
              ? "bg-cyan text-[var(--background)]"
              : "bg-[var(--cdim)] border border-[var(--bhi)] text-cyan hover:bg-[rgba(56,189,248,0.2)]"
          )}
        >
          <BotIcon size={12} />
          AI Analyst
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Run lint:**
```bash
cd frontend && npm run lint
```

- [ ] **Commit:**
```bash
git add frontend/src/components/topbar.tsx
git commit -m "feat: add Topbar with market status, signal count, and AI toggle"
```

---

### Task 10: Chat Panel (Stub)

**Files:**
- Create: `frontend/src/components/chat-panel.tsx`

- [ ] **Create `frontend/src/components/chat-panel.tsx`:**

```tsx
"use client";

import { useEffect, useRef } from "react";
import { BotIcon, SendIcon, XIcon } from "lucide-react";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const SUGGESTIONS = [
  "Analyze my portfolio",
  "Best signals today",
  "What's happening with NVDA?",
  "Top sector momentum",
];

const STUB_MESSAGE =
  "Hi! I'm your AI analyst. Ask me anything about your portfolio or watchlist. (Full AI integration coming soon)";

export function ChatPanel({ isOpen, onClose }: ChatPanelProps) {
  const asideRef = useRef<HTMLElement>(null);
  const handleRef = useRef<HTMLDivElement>(null);

  // Restore saved width and set up drag-resize
  useEffect(() => {
    const savedWidth = localStorage.getItem(STORAGE_KEYS.CHAT_PANEL_WIDTH);
    if (savedWidth) {
      document.documentElement.style.setProperty("--cp", `${savedWidth}px`);
    }

    const handle = handleRef.current;
    const aside = asideRef.current;
    if (!handle || !aside) return;

    const onMouseDown = (e: MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = aside.offsetWidth;
      document.body.classList.add("resizing");

      const onMove = (e: MouseEvent) => {
        const delta = startX - e.clientX; // left drag = wider
        const newWidth = Math.min(520, Math.max(240, startWidth + delta));
        document.documentElement.style.setProperty("--cp", `${newWidth}px`);
      };

      const onUp = () => {
        document.body.classList.remove("resizing");
        const currentWidth = document.documentElement.style
          .getPropertyValue("--cp")
          .replace("px", "");
        localStorage.setItem(STORAGE_KEYS.CHAT_PANEL_WIDTH, currentWidth);
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    };

    handle.addEventListener("mousedown", onMouseDown);
    return () => handle.removeEventListener("mousedown", onMouseDown);
  }, []);

  return (
    <aside
      ref={asideRef}
      className="flex flex-col border-l border-border bg-card flex-shrink-0 relative overflow-hidden"
      style={{
        width: "var(--cp)",
        minWidth: "var(--cp)",
        transform: isOpen ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.25s cubic-bezier(.22,.68,0,1.1)",
      }}
    >
      {/* Drag resize handle */}
      <div
        ref={handleRef}
        className="absolute left-0 top-0 bottom-0 w-[5px] cursor-col-resize z-10 hover:bg-[var(--bhi)] transition-colors"
      />

      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3.5 border-b border-border flex-shrink-0">
        <div>
          <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <span
              className="w-[7px] h-[7px] rounded-full bg-gain"
              style={{ boxShadow: "0 0 5px var(--gain)" }}
            />
            AI Analyst
          </div>
          <p className="text-[10px] text-subtle mt-0.5">Powered by Claude</p>
        </div>
        <button
          onClick={onClose}
          className="w-6 h-6 rounded-[5px] bg-hov border border-border text-muted-foreground hover:text-foreground flex items-center justify-center text-xs"
          aria-label="Close AI panel"
        >
          <XIcon size={12} />
        </button>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3.5 py-3.5 flex flex-col gap-2.5">
        {/* Bot greeting */}
        <div className="flex flex-col gap-0.5">
          <div className="max-w-[85%] px-[11px] py-2 rounded-[10px] rounded-bl-[3px] bg-card2 border border-border text-foreground text-[12px] leading-relaxed">
            {STUB_MESSAGE}
          </div>
          <span className="text-[9.5px] text-subtle px-1">AI Analyst</span>
        </div>
      </div>

      {/* Suggested prompts */}
      <div className="flex flex-wrap gap-1.5 px-3.5 py-2 border-t border-border flex-shrink-0">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="bg-card2 border border-border text-muted-foreground hover:border-[var(--bhi)] hover:text-cyan px-2.5 py-1 rounded-full text-[10.5px] transition-colors whitespace-nowrap"
            disabled
            title="Coming soon — Phase 4"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-border flex-shrink-0">
        <textarea
          className="flex-1 bg-card2 border border-border rounded-lg px-3 py-1.5 text-foreground text-[12px] resize-none outline-none focus:border-[var(--bhi)] placeholder:text-subtle"
          placeholder="Ask about your portfolio... (coming soon)"
          rows={1}
          disabled
        />
        <button
          className="w-8 h-8 rounded-lg bg-cyan flex items-center justify-center flex-shrink-0 opacity-40 cursor-not-allowed"
          disabled
          aria-label="Send message"
        >
          <SendIcon size={14} className="text-[var(--background)]" />
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Commit:**
```bash
git add frontend/src/components/chat-panel.tsx
git commit -m "feat: add ChatPanel stub — resizable, docked, Phase 4 AI integration point"
```

---

### Task 11: Authenticated Layout Shell

**Files:**
- Modify: `frontend/src/app/(authenticated)/layout.tsx`

This wires everything together. The layout becomes a client component.

- [ ] **Replace `frontend/src/app/(authenticated)/layout.tsx`:**

```tsx
"use client";

import { useState, useCallback } from "react";
import { SidebarNav } from "@/components/sidebar-nav";
import { Topbar } from "@/components/topbar";
import { ChatPanel } from "@/components/chat-panel";
import { useAddToWatchlist, useIngestTicker, useWatchlist } from "@/hooks/use-stocks";
import { toast } from "sonner";

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [chatIsOpen, setChatIsOpen] = useState(true); // open by default
  const { data: watchlist } = useWatchlist();
  const addToWatchlist = useAddToWatchlist();
  const ingestTicker = useIngestTicker();

  const handleAddTicker = useCallback(
    async (ticker: string) => {
      const isInWatchlist = watchlist?.some((w) => w.ticker === ticker);
      if (isInWatchlist) {
        toast.info(`${ticker} is already in your watchlist`);
        return;
      }
      toast.loading(`Fetching data for ${ticker}...`, { id: `ingest-${ticker}` });
      try {
        await ingestTicker.mutateAsync(ticker);
        toast.success(`${ticker} data loaded`, { id: `ingest-${ticker}` });
        addToWatchlist.mutate(ticker);
      } catch {
        toast.error(`Failed to fetch data for ${ticker}`, { id: `ingest-${ticker}` });
      }
    },
    [watchlist, ingestTicker, addToWatchlist]
  );

  return (
    <div className="flex overflow-hidden" style={{ height: "100vh" }}>
      <SidebarNav />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar
          chatIsOpen={chatIsOpen}
          onToggleChat={() => setChatIsOpen((v) => !v)}
          onAddTicker={handleAddTicker}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 py-6 animate-fade-in">{children}</div>
        </main>
      </div>

      <ChatPanel
        isOpen={chatIsOpen}
        onClose={() => setChatIsOpen(false)}
      />
    </div>
  );
}
```

**Important:** The `handleAddTicker` logic was previously in `dashboard/page.tsx`. It is now lifted to the layout so the search bar works from any page. Remove the duplicate handler from `dashboard/page.tsx` in the next step.

- [ ] **Update `frontend/src/app/(authenticated)/dashboard/page.tsx`** — remove `handleAddTicker`, `useAddToWatchlist`, `useIngestTicker` (now in layout), and update `<TickerSearch>` usage: the search is now in the Topbar and not rendered on the page. Remove the header section with the search from the dashboard page JSX.

- [ ] **Run lint:**
```bash
cd frontend && npm run lint
```

- [ ] **Verify in browser:** layout shows sidebar + topbar + chat panel side by side.

- [ ] **Delete nav-bar.tsx after confirming zero imports:**
```bash
grep -r "nav-bar" frontend/src
# Must return nothing before deleting
rm frontend/src/components/nav-bar.tsx
```

- [ ] **Commit:**
```bash
git add frontend/src/app/\(authenticated\)/layout.tsx \
        frontend/src/app/\(authenticated\)/dashboard/page.tsx \
        frontend/src/components/nav-bar.tsx
git commit -m "feat: new authenticated layout shell — sidebar + topbar + chat panel"
```

---

## Chunk 3: Core Component Restyling

### Task 12: Sparkline — Polyline Rewrite

**Files:**
- Modify: `frontend/src/components/sparkline.tsx`

- [ ] **Replace `frontend/src/components/sparkline.tsx`:**

```tsx
"use client";

// Sparkline — raw SVG polyline for realistic jagged financial chart appearance.
// Replaces Recharts LineChart (smooth bezier) which looked too smooth for price data.
// Backward compatible: existing `sentiment` prop still works.

import { CSS_VARS } from "@/lib/design-tokens";

function readCssVar(name: string): string {
  if (typeof window === "undefined") return "#22d3a0";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function resolveColor(
  sentiment: "bullish" | "bearish" | "neutral",
  color?: string
): string {
  if (color) return color;
  if (sentiment === "bullish") return readCssVar(CSS_VARS.gain);
  if (sentiment === "bearish") return readCssVar(CSS_VARS.loss);
  return readCssVar(CSS_VARS.neutralSignal);
}

interface SparklineProps {
  data: number[];
  volumes?: number[];
  color?: string;
  sentiment?: "bullish" | "bearish" | "neutral";
  width?: number;
  height?: number;
}

export function Sparkline({
  data,
  volumes,
  color,
  sentiment = "neutral",
  width = 120,
  height = 40,
}: SparklineProps) {
  if (!data || data.length < 2) return null;

  const strokeColor = resolveColor(sentiment, color);
  const VOLUME_ZONE = height * 0.22; // bottom 22% for volume bars
  const PRICE_HEIGHT = height - VOLUME_ZONE - 2;

  const minV = Math.min(...data);
  const maxV = Math.max(...data);
  const range = maxV - minV || 1;

  // Map data to SVG coordinates
  const step = width / (data.length - 1);
  const points = data
    .map((v, i) => {
      const x = i * step;
      const y = PRICE_HEIGHT - ((v - minV) / range) * (PRICE_HEIGHT - 4) + 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Volume bars
  let volumeBars: React.ReactNode = null;
  if (volumes && volumes.length > 0) {
    const maxVol = Math.max(...volumes) || 1;
    const barWidth = (width / volumes.length) * 0.7;
    volumeBars = volumes.map((vol, i) => {
      const barH = (vol / maxVol) * (VOLUME_ZONE - 1);
      const x = i * (width / volumes.length) + (width / volumes.length - barWidth) / 2;
      const y = height - barH;
      return (
        <rect
          key={i}
          x={x.toFixed(1)}
          y={y.toFixed(1)}
          width={barWidth.toFixed(1)}
          height={barH.toFixed(1)}
          fill={strokeColor}
          opacity={0.35}
        />
      );
    });
  }

  const label =
    sentiment === "bullish"
      ? "Bullish trend"
      : sentiment === "bearish"
        ? "Bearish trend"
        : "Price trend";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
      style={{ overflow: "visible" }}
    >
      {volumeBars}
      <polyline
        points={points}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
```

- [ ] **Verify call sites still work** (all pass `sentiment`, no changes needed):
```bash
grep -r "<Sparkline" frontend/src --include="*.tsx"
```

- [ ] **Run lint:**
```bash
cd frontend && npm run lint
```

- [ ] **Commit:**
```bash
git add frontend/src/components/sparkline.tsx
git commit -m "feat: rewrite Sparkline as SVG polyline — jagged financial style + volume bars"
```

---

### Task 13: Index Card Restyle

**Files:**
- Modify: `frontend/src/components/index-card.tsx`

The index card currently shows a count of stocks. The new design shows the index value + sparkline (the data these cards receive doesn't currently include price/sparkline data — keep the card functional but update its visual style to match the new tokens; sparkline can be added when the API provides price data).

- [ ] **Replace `frontend/src/components/index-card.tsx`:**

```tsx
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface IndexCardProps {
  name: string;
  slug: string;
  stockCount: number;
  description: string | null;
  animationDelay?: number;
}

export function IndexCard({
  name,
  slug,
  stockCount,
  description,
  animationDelay = 0,
}: IndexCardProps) {
  return (
    <Link href={`/screener?index=${slug}`}>
      <div
        className={cn(
          "relative overflow-hidden rounded-[var(--radius)] border border-border bg-card p-[11px_13px_9px]",
          "cursor-pointer transition-colors hover:border-[var(--bhi)] hover:bg-hov animate-fade-slide-up"
        )}
        style={{ "--stagger-delay": `${animationDelay}ms` } as React.CSSProperties}
      >
        {/* Top accent line */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-cyan to-transparent" />

        <div className="flex items-baseline justify-between mb-1">
          <span className="text-[10px] font-semibold uppercase tracking-[0.07em] text-muted-foreground">
            {name}
          </span>
          {description && (
            <span className="text-[10px] text-subtle truncate max-w-[120px]">
              {description}
            </span>
          )}
        </div>

        <div className="font-mono text-[17px] font-semibold tracking-tight text-foreground">
          {stockCount}
          <span className="text-[11px] font-normal text-subtle ml-1">stocks</span>
        </div>
      </div>
    </Link>
  );
}

export function IndexCardSkeleton() {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card p-[11px_13px_9px]">
      <Skeleton className="h-3 w-24 mb-2 bg-card2" />
      <Skeleton className="h-5 w-16 bg-card2" />
    </div>
  );
}
```

- [ ] **Commit:**
```bash
git add frontend/src/components/index-card.tsx
git commit -m "feat: restyle IndexCard to navy design system"
```

---

### Task 14: Stock Card Restyle

**Files:**
- Modify: `frontend/src/components/stock-card.tsx`

- [ ] **Replace `frontend/src/components/stock-card.tsx`** with the restyled version. Keep all existing props and logic (staleness check, refresh, acknowledge) — only change the markup/classes:

```tsx
"use client";

import Link from "next/link";
import { XIcon, RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { SignalBadge } from "@/components/signal-badge";
import { RelativeTime } from "./relative-time";
import { cn } from "@/lib/utils";

function isStale(
  priceUpdatedAt: string,
  acknowledgedAt: string | null | undefined
): boolean {
  const priceDate = new Date(priceUpdatedAt).getTime();
  const ageMs = Date.now() - priceDate;
  const isOld = ageMs > 60 * 60 * 1000;
  if (!isOld) return false;
  if (!acknowledgedAt) return true;
  return priceDate > new Date(acknowledgedAt).getTime();
}

function scoreToSignal(score: number | null | undefined): "BUY" | "HOLD" | "SELL" {
  if (score == null) return "HOLD";
  if (score >= 0.6) return "BUY";
  if (score >= 0.4) return "HOLD";
  return "SELL";
}

interface StockCardProps {
  ticker: string;
  name: string | null;
  sector: string | null;
  score?: number | null;
  onRemove: () => void;
  animationDelay?: number;
  currentPrice?: number | null;
  priceUpdatedAt?: string | null;
  onRefresh?: (ticker: string) => void;
  isRefreshing?: boolean;
  priceAcknowledgedAt?: string | null;
  onAcknowledge?: (ticker: string) => void;
}

export function StockCard({
  ticker,
  name,
  sector,
  score,
  onRemove,
  animationDelay = 0,
  currentPrice,
  priceUpdatedAt,
  onRefresh,
  isRefreshing = false,
  priceAcknowledgedAt,
  onAcknowledge,
}: StockCardProps) {
  const signal = scoreToSignal(score);
  const scoreBarPct = score != null ? Math.round(score * 100) : 0;
  const scoreBarColor =
    signal === "BUY" ? "var(--gain)" : signal === "SELL" ? "var(--loss)" : "var(--cyan)";
  const stale =
    priceUpdatedAt ? isStale(priceUpdatedAt, priceAcknowledgedAt) : false;

  return (
    <div
      className="group relative rounded-[var(--radius)] border border-border bg-card p-[12px_13px] flex flex-col gap-2.5 cursor-pointer transition-colors hover:border-[var(--bhi)] hover:bg-hov animate-fade-slide-up"
      style={{ "--stagger-delay": `${animationDelay}ms` } as React.CSSProperties}
    >
      {/* Remove button */}
      <button
        className="absolute top-2 right-2 w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-subtle hover:text-foreground"
        onClick={(e) => { e.preventDefault(); onRemove(); }}
        aria-label={`Remove ${ticker}`}
      >
        <XIcon size={11} />
      </button>

      <Link href={`/stocks/${ticker}`} className="flex flex-col gap-2.5">
        {/* Top row: ticker + price */}
        <div className="flex items-start justify-between pr-5">
          <div>
            <div className="font-mono text-[14px] font-semibold text-foreground">{ticker}</div>
            <div className="text-[10px] text-subtle mt-0.5 truncate max-w-[120px]">{name || "—"}</div>
          </div>
          <div className="text-right">
            {currentPrice != null ? (
              <div className="font-mono text-[14px] font-semibold text-foreground">
                ${currentPrice.toFixed(2)}
              </div>
            ) : (
              <div className="text-[10px] text-subtle">—</div>
            )}
          </div>
        </div>

        {/* Bottom row: signal badge + score bar + refresh */}
        <div className="flex items-center justify-between">
          <SignalBadge signal={signal} />
          <div className="flex items-center gap-2 flex-1 mx-3">
            <div className="flex-1 h-[3px] rounded-full bg-[var(--cdim)]">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${scoreBarPct}%`, background: scoreBarColor }}
              />
            </div>
            <span className="font-mono text-[9.5px] text-subtle">{scoreBarPct}</span>
          </div>

          {/* Refresh controls */}
          <div className="flex items-center gap-0.5">
            {priceUpdatedAt && (
              <span className="text-[9px] text-subtle hidden group-hover:block">
                <RelativeTime date={priceUpdatedAt} />
              </span>
            )}
            <button
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRefresh?.(ticker); }}
              aria-label={`Refresh ${ticker}`}
              className={cn(
                "p-0.5 rounded-full transition-colors",
                isRefreshing && "animate-spin pointer-events-none",
                stale ? "text-warning" : "text-subtle hover:text-muted-foreground"
              )}
            >
              <RefreshCw size={10} />
            </button>
            {stale && onAcknowledge && (
              <button
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onAcknowledge(ticker); }}
                aria-label={`Dismiss stale alert for ${ticker}`}
                className="p-0.5 text-warning hover:text-muted-foreground text-[9px] leading-none"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      </Link>
    </div>
  );
}

export function StockCardSkeleton() {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-card p-[12px_13px] flex flex-col gap-2.5">
      <div className="flex items-start justify-between">
        <div>
          <Skeleton className="h-4 w-14 bg-card2 mb-1" />
          <Skeleton className="h-3 w-20 bg-card2" />
        </div>
        <Skeleton className="h-4 w-16 bg-card2" />
      </div>
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-10 bg-card2" />
        <Skeleton className="h-[3px] flex-1 bg-card2" />
      </div>
    </div>
  );
}
```

Note: `StockCard` now uses `SignalBadge` instead of `ScoreBadge`. Update `ScoreBadge` in Task 15.

- [ ] **Commit:**
```bash
git add frontend/src/components/stock-card.tsx
git commit -m "feat: restyle StockCard to navy design system with signal badge"
```

---

### Task 15: Shared Atom Restyling

**Files:**
- Modify: `frontend/src/components/section-heading.tsx`
- Modify: `frontend/src/components/signal-badge.tsx`
- Modify: `frontend/src/components/score-badge.tsx`
- Modify: `frontend/src/components/change-indicator.tsx`
- Modify: `frontend/src/components/metric-card.tsx`

- [ ] **Update `section-heading.tsx`** — change heading label style:
```tsx
// Change the <h2> or heading element className to:
"text-[9.5px] font-semibold uppercase tracking-[0.1em] text-subtle"
// The action prop slot and overall structure are unchanged.
```

- [ ] **Update `signal-badge.tsx`** — new pill style:
```tsx
// Map signal to className:
const styles = {
  BUY:  "bg-[var(--gdim)] text-gain border border-[rgba(34,211,160,.2)]",
  HOLD: "bg-[var(--wdim)] text-warning border border-[rgba(251,191,36,.18)]",
  SELL: "bg-[var(--ldim)] text-loss border border-[rgba(248,113,113,.2)]",
};
// Base: "font-mono text-[9.5px] font-bold uppercase tracking-[0.06em] rounded-full px-2 py-0.5 inline-flex items-center"
```

- [ ] **Update `score-badge.tsx`** — restyle to match navy tokens (keep existing score-to-label logic, update colours to gain/warning/loss tokens).

- [ ] **Update `change-indicator.tsx`** — positive: `text-gain`, negative: `text-loss`, neutral: `text-subtle`. Add `font-mono` to the numeric value.

- [ ] **Update `metric-card.tsx`** — container: `bg-card2 border border-border rounded-[var(--radius)] p-[10px_13px]`, label: `text-[9px] uppercase tracking-[0.08em] text-subtle mb-1`, value: `font-mono text-[16px] font-semibold text-foreground`.

- [ ] **Commit:**
```bash
git add frontend/src/components/section-heading.tsx \
        frontend/src/components/signal-badge.tsx \
        frontend/src/components/score-badge.tsx \
        frontend/src/components/change-indicator.tsx \
        frontend/src/components/metric-card.tsx
git commit -m "feat: restyle shared atom components to navy design system"
```

---

## Chunk 4: New Dashboard Components

### Task 16: StatTile Component

**Files:**
- Create: `frontend/src/components/stat-tile.tsx`

- [ ] **Create `frontend/src/components/stat-tile.tsx`:**

```tsx
import { cn } from "@/lib/utils";

const ACCENT_GRADIENTS = {
  cyan: "from-cyan to-transparent",
  gain: "from-gain to-transparent",
  loss: "from-loss to-transparent",
  warn: "from-warning to-transparent",
} as const;

interface StatTileProps {
  label: string;
  value?: string;
  sub?: React.ReactNode;
  onClick?: () => void;
  accentColor?: keyof typeof ACCENT_GRADIENTS;
  children?: React.ReactNode;
  className?: string;
}

export function StatTile({
  label,
  value,
  sub,
  onClick,
  accentColor = "cyan",
  children,
  className,
}: StatTileProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "relative overflow-hidden rounded-[var(--radius)] border border-border bg-card p-[13px_14px]",
        "transition-colors hover:border-[var(--bhi)]",
        onClick && "cursor-pointer",
        className
      )}
    >
      {/* Top accent line */}
      <div
        className={cn(
          "absolute top-0 left-0 right-0 h-px bg-gradient-to-r",
          ACCENT_GRADIENTS[accentColor]
        )}
      />

      <div className="text-[9.5px] font-medium uppercase tracking-[0.09em] text-subtle mb-[5px]">
        {label}
      </div>

      {children ? (
        children
      ) : (
        <>
          {value && (
            <div className="font-mono text-[20px] font-bold tracking-tight leading-none text-foreground">
              {value}
            </div>
          )}
          {sub && <div className="mt-1.5 flex items-center gap-1.5">{sub}</div>}
        </>
      )}
    </div>
  );
}
```

- [ ] **Commit:**
```bash
git add frontend/src/components/stat-tile.tsx
git commit -m "feat: add StatTile component for dashboard overview row"
```

---

### Task 17: AllocationDonut Component

**Files:**
- Create: `frontend/src/components/allocation-donut.tsx`

- [ ] **Create `frontend/src/components/allocation-donut.tsx`:**

```tsx
// AllocationDonut — CSS conic-gradient pie chart with legend.
// Used in the Dashboard Overview tiles row.

const DONUT_COLORS = [
  "#38bdf8", // cyan
  "#fbbf24", // warning/amber
  "#a78bfa", // purple
  "#22d3a0", // gain/teal
  "#f87171", // loss/red
  "#fb923c", // orange
] as const;

interface AllocationItem {
  sector: string;
  pct: number;
  color: string;
}

interface AllocationDonutProps {
  allocations: AllocationItem[];
  stockCount?: number;
}

function buildGradient(allocations: AllocationItem[]): string {
  let cumulative = 0;
  const stops = allocations.map(({ pct, color }) => {
    const start = cumulative;
    cumulative += pct;
    return `${color} ${start.toFixed(1)}% ${cumulative.toFixed(1)}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

export function AllocationDonut({ allocations, stockCount }: AllocationDonutProps) {
  if (!allocations.length) {
    return (
      <div className="text-[10px] text-subtle mt-2">No positions</div>
    );
  }

  const gradient = buildGradient(allocations);
  const displayed = allocations.slice(0, 3);
  const remainder = allocations.length - 3;

  return (
    <div className="flex items-center gap-2.5 mt-2">
      {/* Donut */}
      <div
        className="w-[72px] h-[72px] rounded-full flex-shrink-0 flex items-center justify-center"
        style={{ background: gradient }}
      >
        <div className="w-[46px] h-[46px] rounded-full bg-card flex items-center justify-center">
          <div className="text-center leading-tight">
            <div className="font-mono text-[12px] font-bold text-foreground">
              {stockCount ?? allocations.length}
            </div>
            <div className="text-[8px] text-subtle">stocks</div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-col gap-1 flex-1">
        {displayed.map((a) => (
          <div key={a.sector} className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: a.color }}
            />
            <span className="text-[10px] text-muted-foreground flex-1 truncate">
              {a.sector}
            </span>
            <span className="font-mono text-[10px] text-subtle">
              {a.pct.toFixed(0)}%
            </span>
          </div>
        ))}
        {remainder > 0 && (
          <div className="text-[9px] text-subtle">+{remainder} more</div>
        )}
      </div>
    </div>
  );
}

export { DONUT_COLORS };
```

- [ ] **Commit:**
```bash
git add frontend/src/components/allocation-donut.tsx
git commit -m "feat: add AllocationDonut component — CSS conic-gradient with legend"
```

---

### Task 18: Portfolio Drawer Component

**Files:**
- Create: `frontend/src/components/portfolio-drawer.tsx`

- [ ] **Create `frontend/src/components/portfolio-drawer.tsx`:**

```tsx
"use client";

import { XIcon } from "lucide-react";
import { PortfolioValueChart } from "@/components/portfolio-value-chart";
import { usePortfolioSummary, usePortfolioHistory } from "@/hooks/use-stocks";
import { formatCurrency } from "@/lib/format";

interface PortfolioDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  chatIsOpen: boolean;
}

export function PortfolioDrawer({ isOpen, onClose, chatIsOpen }: PortfolioDrawerProps) {
  const { data: summary } = usePortfolioSummary();
  const { data: snapshots = [] } = usePortfolioHistory(365);

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40"
          style={{
            background: "rgba(7,13,24,.7)",
            backdropFilter: "blur(3px)",
          }}
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className="fixed bottom-0 z-50 bg-card overflow-auto"
        style={{
          left: "var(--sw)",
          right: chatIsOpen ? "var(--cp)" : 0,
          height: isOpen ? "62vh" : 0,
          overflow: isOpen ? "auto" : "hidden",
          borderTop: "1px solid var(--bhi)",
          borderRadius: "14px 14px 0 0",
          boxShadow: "0 -20px 60px rgba(56,189,248,.08)",
          transition:
            "height 0.3s cubic-bezier(.22,.68,0,1.1), right 0.25s cubic-bezier(.22,.68,0,1.1)",
        }}
      >
        <div className="px-7 pb-7 pt-5">
          {/* Drag handle */}
          <div
            className="w-9 h-1 rounded-full bg-border mx-auto mb-5 cursor-pointer"
            onClick={onClose}
          />

          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-5 w-7 h-7 rounded-[6px] bg-hov border border-border text-muted-foreground hover:text-foreground flex items-center justify-center"
            aria-label="Close portfolio chart"
          >
            <XIcon size={13} />
          </button>

          {/* Header */}
          <div className="flex items-baseline gap-3 mb-4">
            <div className="font-mono text-[30px] font-bold tracking-tight text-foreground">
              {summary ? formatCurrency(summary.total_value) : "—"}
            </div>
            <div className="text-[11px] text-subtle">Portfolio Value</div>
          </div>

          {/* Full-width chart */}
          <PortfolioValueChart snapshots={snapshots} />

          {/* Stats row */}
          {/* PortfolioSummary fields (from types/api.ts):
              total_value, total_cost_basis, unrealized_pnl, unrealized_pnl_pct,
              position_count, sectors. No day_gain or cash fields exist in the API. */}
          {summary && (
            <div className="grid grid-cols-4 gap-2.5 mt-5">
              {[
                { label: "Unrealized P&L", value: formatCurrency(summary.unrealized_pnl) },
                { label: "P&L %", value: `${summary.unrealized_pnl_pct.toFixed(2)}%` },
                { label: "Positions", value: String(summary.position_count) },
                { label: "Cost Basis", value: formatCurrency(summary.total_cost_basis) },
              ].map((s) => (
                <div key={s.label} className="bg-card2 rounded-lg p-[10px_13px]">
                  <div className="text-[9px] uppercase tracking-[0.08em] text-subtle mb-1">
                    {s.label}
                  </div>
                  <div className="font-mono text-[16px] font-semibold text-foreground">
                    {s.value}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
```

Note: Check `PortfolioSummary` type in `types/api.ts` and adjust field names (`total_gain`, `day_gain`, `position_count`, `cash`) to match the actual API response shape.

- [ ] **Commit:**
```bash
git add frontend/src/components/portfolio-drawer.tsx
git commit -m "feat: add PortfolioDrawer — bottom slide-up chart panel"
```

---

### Task 19: Wire Dashboard Overview Tiles

**Files:**
- Modify: `frontend/src/app/(authenticated)/dashboard/page.tsx`

- [ ] **Update `dashboard/page.tsx`** to add the Overview tiles row between Market Indexes and Watchlist, and remove the now-redundant header+search (moved to Topbar in layout):

```tsx
// Add new imports:
import { StatTile } from "@/components/stat-tile";
import { AllocationDonut, DONUT_COLORS } from "@/components/allocation-donut";
import { PortfolioDrawer } from "@/components/portfolio-drawer";
import { ChangeIndicator } from "@/components/change-indicator";
import { usePortfolioSummary, usePositions } from "@/hooks/use-stocks";
import { formatCurrency } from "@/lib/format";

// Add state at top of component:
const [drawerOpen, setDrawerOpen] = useState(false);
// NOTE: chatIsOpen is needed by PortfolioDrawer to offset its right edge.
// For now, pass false (drawer spans full width). A React context can be added
// in a follow-up task to sync this with the layout's chatIsOpen state.
// Known limitation: drawer may overlap chat panel if both are open.
// Follow-up task: create ChatStateContext in layout and consume here.
const chatIsOpen = false; // TODO: wire from layout context

// Add data hooks:
const { data: summary } = usePortfolioSummary();
const { data: positions } = usePositions();

// Derive allocations:
const allocations = useMemo(() => {
  if (!positions) return [];
  const sectorTotals: Record<string, number> = {};
  let total = 0;
  positions.forEach((p) => {
    const sector = p.sector ?? "Other";
    sectorTotals[sector] = (sectorTotals[sector] ?? 0) + (p.market_value ?? 0);
    total += p.market_value ?? 0;
  });
  return Object.entries(sectorTotals).map(([sector, value], i) => ({
    sector,
    pct: total > 0 ? (value / total) * 100 : 0,
    color: DONUT_COLORS[i % DONUT_COLORS.length],
  }));
}, [positions]);

// Derive signal counts:
const signalCounts = useMemo(() => {
  if (!watchlist) return { buy: 0, hold: 0, sell: 0 };
  return watchlist.reduce(
    (acc, w) => {
      const score = w.composite_score ?? 0;
      if (score >= 0.6) acc.buy++;
      else if (score >= 0.4) acc.hold++;
      else acc.sell++;
      return acc;
    },
    { buy: 0, hold: 0, sell: 0 }
  );
}, [watchlist]);

// Top signal:
const topSignal = useMemo(() => {
  if (!watchlist) return null;
  return watchlist
    .filter((w) => (w.composite_score ?? 0) >= 0.6)
    .sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0))[0] ?? null;
}, [watchlist]);
```

Add between Market Indexes section and Watchlist section:
```tsx
{/* Overview tiles */}
<section>
  <SectionHeading>Overview</SectionHeading>
  <div className="grid grid-cols-5 gap-[9px]">
    {/* Portfolio Value — no day_gain in API; show unrealized_pnl as sub */}
    <StatTile
      label="Portfolio Value"
      value={summary ? formatCurrency(summary.total_value) : "—"}
      sub={
        summary?.unrealized_pnl != null ? (
          <ChangeIndicator value={summary.unrealized_pnl} format="currency" />
        ) : undefined
      }
      accentColor="cyan"
      onClick={() => setDrawerOpen(true)}
    />

    {/* Unrealized P&L — uses unrealized_pnl and unrealized_pnl_pct from PortfolioSummary */}
    <StatTile
      label="Unrealized P&L"
      value={summary ? formatCurrency(summary.unrealized_pnl) : "—"}
      sub={
        summary?.unrealized_pnl_pct != null ? (
          <ChangeIndicator value={summary.unrealized_pnl_pct} format="percent" />
        ) : undefined
      }
      accentColor={
        (summary?.unrealized_pnl ?? 0) >= 0 ? "gain" : "loss"
      }
    />

    {/* Signals */}
    <StatTile label="Signals" accentColor="warn">
      <div className="grid grid-cols-3 gap-[5px] mt-[7px]">
        <div className="text-center rounded-[6px] py-[7px] bg-[var(--gdim)]">
          <div className="font-mono text-[20px] font-bold leading-none text-gain">{signalCounts.buy}</div>
          <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-gain">Buy</div>
        </div>
        <div className="text-center rounded-[6px] py-[7px] bg-[var(--wdim)]">
          <div className="font-mono text-[20px] font-bold leading-none text-warning">{signalCounts.hold}</div>
          <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-warning">Hold</div>
        </div>
        <div className="text-center rounded-[6px] py-[7px] bg-[var(--ldim)]">
          <div className="font-mono text-[20px] font-bold leading-none text-loss">{signalCounts.sell}</div>
          <div className="text-[9px] font-semibold tracking-[0.07em] uppercase mt-0.5 text-loss">Sell</div>
        </div>
      </div>
    </StatTile>

    {/* Top Signal */}
    <StatTile label="Top Signal" accentColor="gain">
      {topSignal ? (
        <div className="mt-1">
          <div className="font-mono text-[18px] font-bold text-foreground">{topSignal.ticker}</div>
          <div className="text-[10px] text-subtle truncate">{topSignal.name}</div>
          <div className="font-mono text-[11px] text-gain mt-1">
            Score: {Math.round((topSignal.composite_score ?? 0) * 100)}
          </div>
        </div>
      ) : (
        <div className="text-[10px] text-subtle mt-2">No strong signals</div>
      )}
    </StatTile>

    {/* Allocation */}
    <StatTile label="Allocation" accentColor="cyan">
      <AllocationDonut
        allocations={allocations}
        stockCount={positions?.length}
      />
    </StatTile>
  </div>
</section>

{/* Portfolio Drawer */}
<PortfolioDrawer
  isOpen={drawerOpen}
  onClose={() => setDrawerOpen(false)}
  chatIsOpen={chatIsOpen}
/>
```

- [ ] **Check `PortfolioSummary` type** for correct field names:
```bash
grep -n "total_gain\|day_gain\|position_count\|total_value" frontend/src/types/api.ts
```
Adjust field names in the tile JSX to match actual API types.

- [ ] **Run lint:**
```bash
cd frontend && npm run lint
```

- [ ] **Commit:**
```bash
git add frontend/src/app/\(authenticated\)/dashboard/page.tsx
git commit -m "feat: add Overview tiles row to Dashboard with portfolio drawer"
```

---

## Chunk 5: Remaining Component Token Updates

### Task 20: Empty/Error States + Breadcrumbs + Relative Time

**Files:**
- Modify: `frontend/src/components/empty-state.tsx`
- Modify: `frontend/src/components/error-state.tsx`
- Modify: `frontend/src/components/breadcrumbs.tsx`
- Modify: `frontend/src/components/relative-time.tsx`

- [ ] For each file, update colour classes to use new tokens:
  - Icon colours: `text-subtle`
  - Title text: `text-foreground`
  - Description text: `text-muted-foreground`
  - Breadcrumb separators and inactive links: `text-subtle`
  - Relative time: `text-subtle`

- [ ] **Commit:**
```bash
git add frontend/src/components/empty-state.tsx \
        frontend/src/components/error-state.tsx \
        frontend/src/components/breadcrumbs.tsx \
        frontend/src/components/relative-time.tsx
git commit -m "feat: update utility components to navy tokens"
```

---

### Task 21: Screener Components

**Files:**
- Modify: `frontend/src/components/screener-filters.tsx`
- Modify: `frontend/src/components/screener-grid.tsx`
- Modify: `frontend/src/components/screener-table.tsx`
- Modify: `frontend/src/components/pagination-controls.tsx`
- Modify: `frontend/src/components/sector-filter.tsx`

- [ ] **Token updates:**
  - Table: `border-border`, row hover `hover:bg-hov`, header cells `text-subtle uppercase text-[9.5px] tracking-[0.1em]`
  - Filter chips: `bg-card2 border-border`, active: `border-[var(--bhi)] text-cyan`
  - Pagination buttons: `bg-card2 border-border hover:bg-hov`

- [ ] **Commit:**
```bash
git add frontend/src/components/screener-filters.tsx \
        frontend/src/components/screener-grid.tsx \
        frontend/src/components/screener-table.tsx \
        frontend/src/components/pagination-controls.tsx \
        frontend/src/components/sector-filter.tsx
git commit -m "feat: update screener components to navy tokens"
```

---

### Task 22: Stock Detail Components

**Files:**
- Modify: `frontend/src/components/stock-header.tsx`
- Modify: `frontend/src/components/signal-cards.tsx`
- Modify: `frontend/src/components/signal-history-chart.tsx`
- Modify: `frontend/src/components/signal-meter.tsx`
- Modify: `frontend/src/components/fundamentals-card.tsx`
- Modify: `frontend/src/components/dividend-card.tsx`
- Modify: `frontend/src/components/risk-return-card.tsx`
- Modify: `frontend/src/components/chart-tooltip.tsx`
- Modify: `frontend/src/components/price-chart.tsx`

- [ ] **Token updates:**
  - Card surfaces: `bg-card` / `bg-card2`
  - Ticker/price labels: `font-mono`
  - Chart colors: already via `useChartColors()` — verify they resolve correctly with new tokens
  - `stock-header.tsx`: ticker `font-mono text-2xl font-bold`, price `font-mono`

- [ ] **Commit:**
```bash
git add frontend/src/components/stock-header.tsx \
        frontend/src/components/signal-cards.tsx \
        frontend/src/components/signal-history-chart.tsx \
        frontend/src/components/signal-meter.tsx \
        frontend/src/components/fundamentals-card.tsx \
        frontend/src/components/dividend-card.tsx \
        frontend/src/components/risk-return-card.tsx \
        frontend/src/components/chart-tooltip.tsx \
        frontend/src/components/price-chart.tsx
git commit -m "feat: update stock detail components to navy tokens"
```

---

### Task 23: Portfolio Components

**Files:**
- Modify: `frontend/src/components/portfolio-value-chart.tsx`
- Modify: `frontend/src/components/rebalancing-panel.tsx`
- Modify: `frontend/src/components/portfolio-settings-sheet.tsx`
- Modify: `frontend/src/components/log-transaction-dialog.tsx`
- Modify: `frontend/src/components/ticker-search.tsx`

- [ ] **Token updates:**
  - Sheet/dialog: `bg-card border-border`
  - Inputs: `bg-card2 border-border focus:border-[var(--bhi)]`
  - `ticker-search.tsx`: input `bg-card border-border`, results popover `bg-card2`
  - `rebalancing-panel.tsx`: already uses `text-warning` (added in session 27) — verify it still resolves

- [ ] **Commit:**
```bash
git add frontend/src/components/portfolio-value-chart.tsx \
        frontend/src/components/rebalancing-panel.tsx \
        frontend/src/components/portfolio-settings-sheet.tsx \
        frontend/src/components/log-transaction-dialog.tsx \
        frontend/src/components/ticker-search.tsx
git commit -m "feat: update portfolio components to navy tokens"
```

---

## Chunk 6: Tests + Final Verification

### Task 24: Write Tests for New Components

**Files:**
- Create: `frontend/src/__tests__/components/stat-tile.test.tsx`
- Create: `frontend/src/__tests__/components/allocation-donut.test.tsx`
- Create: `frontend/src/__tests__/components/portfolio-drawer.test.tsx`
- Create: `frontend/src/__tests__/components/sidebar-nav.test.tsx`
- Create: `frontend/src/__tests__/components/chat-panel.test.tsx`

- [ ] **`stat-tile.test.tsx`:**
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatTile } from "@/components/stat-tile";

test("renders label and value", () => {
  render(<StatTile label="Portfolio Value" value="$124,830" />);
  expect(screen.getByText("Portfolio Value")).toBeInTheDocument();
  expect(screen.getByText("$124,830")).toBeInTheDocument();
});

test("renders children instead of value when provided", () => {
  render(<StatTile label="Signals"><span>custom content</span></StatTile>);
  expect(screen.getByText("custom content")).toBeInTheDocument();
});

test("calls onClick when clicked", async () => {
  const onClick = jest.fn();
  render(<StatTile label="Test" value="123" onClick={onClick} />);
  await userEvent.click(screen.getByText("Test").closest("div")!);
  expect(onClick).toHaveBeenCalledTimes(1);
});
```

- [ ] **First, export `buildGradient` from `allocation-donut.tsx`** — add `export` keyword:
```tsx
export function buildGradient(allocations: AllocationItem[]): string {
```

- [ ] **`allocation-donut.test.tsx`:**
```tsx
import { render, screen } from "@testing-library/react";
import { AllocationDonut, buildGradient } from "@/components/allocation-donut";

test("buildGradient produces correct conic-gradient stops", () => {
  const result = buildGradient([
    { sector: "Tech", pct: 60, color: "#38bdf8" },
    { sector: "Finance", pct: 40, color: "#fbbf24" },
  ]);
  expect(result).toContain("#38bdf8 0.0% 60.0%");
  expect(result).toContain("#fbbf24 60.0% 100.0%");
});

test("renders 'No positions' when allocations is empty", () => {
  render(<AllocationDonut allocations={[]} />);
  expect(screen.getByText("No positions")).toBeInTheDocument();
});

test("renders sector legend items", () => {
  render(
    <AllocationDonut
      allocations={[
        { sector: "Tech", pct: 60, color: "#38bdf8" },
        { sector: "Finance", pct: 40, color: "#fbbf24" },
      ]}
      stockCount={5}
    />
  );
  expect(screen.getByText("Tech")).toBeInTheDocument();
  expect(screen.getByText("Finance")).toBeInTheDocument();
});
```

- [ ] **`sidebar-nav.test.tsx`** — test active link detection:
```tsx
// Mock usePathname to return "/dashboard"
// Assert Dashboard link has active styling class
```

- [ ] **`portfolio-drawer.test.tsx`:**
```tsx
import { render, screen } from "@testing-library/react";
import { PortfolioDrawer } from "@/components/portfolio-drawer";

// Mock the hooks used inside PortfolioDrawer
jest.mock("@/hooks/use-stocks", () => ({
  usePortfolioSummary: () => ({ data: null }),
  usePortfolioHistory: () => ({ data: [] }),
}));

test("does not render content when closed (height 0)", () => {
  const { container } = render(
    <PortfolioDrawer isOpen={false} onClose={jest.fn()} chatIsOpen={false} />
  );
  const drawer = container.querySelector("[style*='height: 0']") ??
                 container.querySelector("[style*='height:0']");
  expect(drawer).toBeTruthy();
});

test("renders when open", () => {
  render(
    <PortfolioDrawer isOpen={true} onClose={jest.fn()} chatIsOpen={false} />
  );
  expect(screen.getByLabelText("Close portfolio chart")).toBeInTheDocument();
});
```

- [ ] **`chat-panel.test.tsx`** — test open/closed transform:
```tsx
import { render } from "@testing-library/react";
import { ChatPanel } from "@/components/chat-panel";

test("has translateX(100%) transform when closed", () => {
  const { container } = render(<ChatPanel isOpen={false} onClose={jest.fn()} />);
  const aside = container.querySelector("aside");
  expect(aside?.style.transform).toBe("translateX(100%)");
});

test("has translateX(0) transform when open", () => {
  const { container } = render(<ChatPanel isOpen={true} onClose={jest.fn()} />);
  const aside = container.querySelector("aside");
  expect(aside?.style.transform).toBe("translateX(0)");
});
```

- [ ] **Run all frontend tests:**
```bash
cd frontend && npm test
```

- [ ] **Commit:**
```bash
git add frontend/src/__tests__/
git commit -m "test: add tests for new UI components (StatTile, AllocationDonut, SidebarNav, ChatPanel)"
```

---

### Task 25: Final Lint + Visual Check

- [ ] **Run full lint:**
```bash
cd frontend && npm run lint
```
Fix any remaining issues. Zero warnings/errors required.

- [ ] **Build check** (catch type errors not caught by lint):
```bash
cd frontend && npm run build
```
Expected: successful build, no type errors.

- [ ] **Visual check:** Open `http://localhost:3000` alongside `prototype-ui.html` and verify:
  - [ ] Navy dark background everywhere
  - [ ] Sora font for labels, JetBrains Mono for numbers
  - [ ] 54px icon sidebar with tooltips
  - [ ] Chat panel open by default, resizable
  - [ ] Dashboard shows 3 index cards + 5 stat tiles + 4-col watchlist
  - [ ] Portfolio Value tile click opens bottom drawer
  - [ ] AI Analyst button toggles chat panel
  - [ ] Market status chip shows correct open/closed state

- [ ] **Commit any final fixes, then tag the shell complete:**
```bash
git commit -m "feat: UI redesign complete — navy command center theme + icon sidebar + chat panel"
```

---

## Summary

| Phase | Tasks | Key Deliverables |
|-------|-------|-----------------|
| Chunk 1 | 1–6 | Tokens, fonts, providers, dark-only |
| Chunk 2 | 7–11 | Shell layout: sidebar, topbar, chat panel |
| Chunk 3 | 12–15 | Sparkline rewrite, core card restyling |
| Chunk 4 | 16–19 | New components: StatTile, Donut, Drawer, Dashboard wiring |
| Chunk 5 | 20–23 | All remaining component token updates |
| Chunk 6 | 24–25 | Tests + final verification |

**On context loss:** Resume using the Implementation Order in the spec (`docs/superpowers/specs/2026-03-15-ui-redesign-phase-4-shell-design.md`). Each task above maps to a numbered step. Check `git log --oneline -30` to see which commits are done, then find the corresponding task number and resume from there.
