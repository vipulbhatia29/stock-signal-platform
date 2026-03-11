# Entry Animations + prefers-reduced-motion — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add staggered fade-slide-up entry animations to cards and table rows across the platform, with a global `prefers-reduced-motion` rule that collapses all motion to instant.

**Architecture:** Define two CSS keyframes + two Tailwind utility classes in `globals.css`. Apply them via a single `animate-fade-slide-up` class + an inline `--stagger-delay` CSS custom property. Route-level fade is applied directly to the `<main>` element in the authenticated layout (no client component or `usePathname` — the CSS animation replays on every page render naturally). A global `@media (prefers-reduced-motion: reduce)` rule handles accessibility with zero per-component logic.

**Tech Stack:** Next.js App Router, Tailwind CSS v4, `tw-animate-css` (already imported), TypeScript strict mode.

---

## Chunk 1: Animation foundation in globals.css

### Task 1: Add keyframes, utility classes, and prefers-reduced-motion rule

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Check if `tw-animate-css` already defines `animate-fade-in`**

```bash
grep -r "fade-in\|fade-slide" frontend/node_modules/tw-animate-css/ --include="*.css" -l
```

If it defines `animate-fade-in`, rename ours to `animate-page-fade-in` to avoid conflicts. Otherwise, proceed as below.

- [ ] **Step 2: Append the following to the END of `frontend/src/app/globals.css` (after all existing content):**

```css
/* ── Entry animation keyframes ─────────────────────────────────────────────── */

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes fade-slide-up {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Utility classes for entry animations */
@layer utilities {
  .animate-fade-in {
    animation: fade-in 0.4s ease both;
  }
  .animate-fade-slide-up {
    animation: fade-slide-up 0.4s cubic-bezier(.22,.68,0,1.2) var(--stagger-delay, 0ms) both;
  }
}

/* ── Accessibility: honour prefers-reduced-motion ───────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-delay: 0ms !important;
  }
}
```

> **Note:** If Step 1 revealed a conflict with `tw-animate-css`, rename `animate-fade-in` → `animate-page-fade-in` in both the `@layer utilities` block here and in Task 2 below.

- [ ] **Step 3: Run lint to verify no CSS errors**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat: add fade-in and fade-slide-up animation utilities + prefers-reduced-motion rule"
```

---

## Chunk 2: Page-level route transition

### Task 2: Fade-in on route change (authenticated layout)

**Files:**
- Modify: `frontend/src/app/(authenticated)/layout.tsx`

The correct App Router approach is to apply `animate-fade-in` directly to the `<main>` element. Because each page renders fresh HTML, the browser replays the CSS `animation: fade-in` naturally on every navigation — no `usePathname`, no client component, no `key` prop needed. This avoids the flash-of-empty-content caused by the `key={pathname}` pattern.

Current file content (14 lines):

```tsx
import { NavBar } from "@/components/nav-bar";

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
```

- [ ] **Step 1: Add `animate-fade-in` to the `<main>` element:**

Replace the entire file with:

```tsx
import { NavBar } from "@/components/nav-bar";

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="mx-auto max-w-7xl px-4 py-6 animate-fade-in">
        {children}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 3: Manually verify** — start dev server (`npm run dev`), navigate between Dashboard and Screener. Each page fades in over ~400ms. No flash of empty content.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/(authenticated)/layout.tsx
git commit -m "feat: add fade-in page transition via animate-fade-in on main element"
```

---

## Chunk 3: Dashboard — index cards and watchlist stock cards

### Task 3: Add animationDelay prop to IndexCard

**Files:**
- Modify: `frontend/src/components/index-card.tsx`

The current `<Link>` in `IndexCard` renders as an inline `<a>`. CSS `transform` (required for the slide-up) is ignored on inline elements. Apply the animation to the `<Card>` (block element) inside, not the `<Link>`.

Current file structure:
- `IndexCardProps` interface (lines 12-17): `name`, `slug`, `stockCount`, `description`
- `<Link>` wraps `<Card>` (line 26)
- `<Card>` has `className="cursor-pointer transition-colors hover:border-foreground/20"` (line 27)

- [ ] **Step 1: Add `animationDelay` to `IndexCardProps` and apply to `<Card>`:**

Replace the entire file with:

```tsx
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/metric-card";

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
      <Card
        className="cursor-pointer transition-colors hover:border-foreground/20 animate-fade-slide-up"
        style={{ '--stagger-delay': `${animationDelay}ms` } as React.CSSProperties}
      >
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{name}</CardTitle>
          {description && (
            <CardDescription className="text-xs">{description}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <MetricCard
            label="stocks"
            value={stockCount}
            valueClassName="text-2xl font-semibold tabular-nums"
          />
        </CardContent>
      </Card>
    </Link>
  );
}

export function IndexCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-16" />
        <Skeleton className="mt-1 h-3 w-12" />
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/index-card.tsx
git commit -m "feat: add animationDelay prop to IndexCard, animate Card (not Link)"
```

### Task 4: Add animationDelay prop to StockCard

**Files:**
- Modify: `frontend/src/components/stock-card.tsx`

Current `StockCardProps` (lines 10-16): `ticker`, `name`, `sector`, `score`, `onRemove`.
Root element is `<Card className="group relative transition-colors hover:border-foreground/20">` (line 26).

- [ ] **Step 1: Add `animationDelay` to `StockCardProps` and apply to root `<Card>`:**

Replace the entire file with:

```tsx
"use client";

import Link from "next/link";
import { XIcon } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreBadge } from "@/components/score-badge";

interface StockCardProps {
  ticker: string;
  name: string | null;
  sector: string | null;
  score?: number | null;
  onRemove: () => void;
  animationDelay?: number;
}

export function StockCard({
  ticker,
  name,
  sector,
  score,
  onRemove,
  animationDelay = 0,
}: StockCardProps) {
  return (
    <Card
      className="group relative transition-colors hover:border-foreground/20 animate-fade-slide-up"
      style={{ '--stagger-delay': `${animationDelay}ms` } as React.CSSProperties}
    >
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 size-6 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={(e) => {
          e.preventDefault();
          onRemove();
        }}
        aria-label={`Remove ${ticker}`}
      >
        <XIcon className="size-3.5" />
      </Button>
      <Link href={`/stocks/${ticker}`}>
        <CardHeader className="pb-1">
          <div className="flex items-center justify-between pr-6">
            <span className="font-mono text-base font-semibold">{ticker}</span>
            <ScoreBadge score={score ?? null} size="sm" />
          </div>
        </CardHeader>
        <CardContent className="space-y-1">
          <p className="truncate text-sm text-muted-foreground">
            {name || "—"}
          </p>
          {sector && (
            <span className="inline-flex rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground">
              {sector}
            </span>
          )}
        </CardContent>
      </Link>
    </Card>
  );
}

export function StockCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-1">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-10" />
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-5 w-16" />
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stock-card.tsx
git commit -m "feat: add animationDelay prop to StockCard"
```

### Task 5: Pass stagger delays from dashboard page

**Files:**
- Modify: `frontend/src/app/(authenticated)/dashboard/page.tsx`

- [ ] **Step 1: Read the full dashboard page render block (from line 60 to end)**

Open `frontend/src/app/(authenticated)/dashboard/page.tsx` and read from line 60 to end to find the exact JSX for `indexes.map(...)` and `filteredWatchlist.map(...)`.

- [ ] **Step 2: Pass `animationDelay` to each `<IndexCard>` — stagger: first card 0ms, second 80ms, third 160ms**

In the `indexes.map((index) => ...)` render, add the `i` index variable and `animationDelay` prop:

```tsx
{indexes.map((index, i) => (
  <IndexCard
    key={index.slug}
    name={index.name}
    slug={index.slug}
    stockCount={index.stock_count}
    description={index.description}
    animationDelay={i * 80}
  />
))}
```

- [ ] **Step 3: Pass `animationDelay` to each `<StockCard>` — stagger 60ms × index, first 8 cards only**

In the `filteredWatchlist.map((item) => ...)` render, add the `i` index variable and `animationDelay` prop:

```tsx
{filteredWatchlist.map((item, i) => (
  <StockCard
    key={item.ticker}
    ticker={item.ticker}
    name={item.name}
    sector={item.sector}
    score={item.score}
    onRemove={() => handleRemoveTicker(item.ticker)}
    animationDelay={Math.min(i, 7) * 60}
  />
))}
```

> `Math.min(i, 7) * 60` means cards 0–7 animate at 0ms–420ms; cards 8+ all get 420ms (near-instant relative to page load — effectively no stagger once off-screen).

- [ ] **Step 4: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 5: Manually verify** — open Dashboard. Index cards stagger (0ms, 80ms, 160ms). Watchlist cards stagger 60ms apart. Refresh to replay.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/(authenticated)/dashboard/page.tsx
git commit -m "feat: stagger index cards and watchlist cards on dashboard"
```

---

## Chunk 4: Screener — table rows and grid cards

### Task 6: Animate screener table rows

**Files:**
- Modify: `frontend/src/components/screener-table.tsx`

The current `<TableBody>` render (lines 260-283):

```tsx
{items.map((item) => {
  const sentiment = scoreToSentiment(item.composite_score);
  const rowBg =
    sentiment === "neutral" ? "" : SENTIMENT_BG_CLASSES[sentiment];

  return (
    <TableRow
      key={item.ticker}
      className={cn(rowBg, "cursor-pointer hover:bg-accent/50")}
      onClick={() => router.push(`/stocks/${item.ticker}`)}
    >
      {columns.map((col) => (
        <TableCell key={col.key} className={cn(rowPadding, textSize)}>
          {col.render(item)}
        </TableCell>
      ))}
    </TableRow>
  );
})}
```

- [ ] **Step 1: Add `i` to the map and conditionally apply `animate-fade-slide-up` to the first 12 rows. Preserve the existing `rowBg` neutral guard and `hover:bg-accent/50`:**

Replace the `items.map(...)` block with:

```tsx
{items.map((item, i) => {
  const sentiment = scoreToSentiment(item.composite_score);
  const rowBg =
    sentiment === "neutral" ? "" : SENTIMENT_BG_CLASSES[sentiment];

  return (
    <TableRow
      key={item.ticker}
      className={cn(
        rowBg,
        "cursor-pointer hover:bg-accent/50",
        i < 12 && "animate-fade-slide-up",
      )}
      style={
        i < 12
          ? ({ '--stagger-delay': `${i * 30}ms` } as React.CSSProperties)
          : undefined
      }
      onClick={() => router.push(`/stocks/${item.ticker}`)}
    >
      {columns.map((col) => (
        <TableCell key={col.key} className={cn(rowPadding, textSize)}>
          {col.render(item)}
        </TableCell>
      ))}
    </TableRow>
  );
})}
```

- [ ] **Step 2: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 3: Manually verify** — open Screener in list view. First 12 rows slide up and fade in with 30ms stagger. Rows 13+ appear immediately.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/screener-table.tsx
git commit -m "feat: stagger first 12 screener table rows on load"
```

### Task 7: Animate screener grid cards

**Files:**
- Modify: `frontend/src/components/screener-grid.tsx`

The private `StockCard` component (lines 17-96) renders a `<div>` as its root element (line 24). The `ScreenerGrid` renders items via `items.map((item) => <StockCard key={item.ticker} item={item} />)` (lines 134-136).

The cleanest approach is to add an `animationDelay` prop to the private `StockCard` and pass `i * 40` from the map — no wrapper div needed.

- [ ] **Step 1: Add `animationDelay` prop to the private `StockCard` component (lines 17-96)**

Change the function signature from:
```tsx
function StockCard({ item }: { item: BulkSignalItem }) {
```
to:
```tsx
function StockCard({ item, animationDelay = 0 }: { item: BulkSignalItem; animationDelay?: number }) {
```

Add `animate-fade-slide-up` and `--stagger-delay` to the root `<div>` (currently line 24-36):
```tsx
<div
  className={cn(
    "group rounded-lg border bg-card overflow-hidden cursor-pointer hover:border-primary/50 transition-colors",
    "animate-fade-slide-up",
  )}
  style={{ '--stagger-delay': `${animationDelay}ms` } as React.CSSProperties}
  onClick={() => router.push(`/stocks/${item.ticker}`)}
  role="button"
  tabIndex={0}
  aria-label={`View ${item.ticker} — ${item.name}`}
  onKeyDown={(e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      router.push(`/stocks/${item.ticker}`);
    }
  }}
>
```

- [ ] **Step 2: Pass `animationDelay` in `ScreenerGrid`'s map — first 12 cards stagger at 40ms intervals**

Change the `items.map(...)` call (lines 134-136) from:
```tsx
{items.map((item) => (
  <StockCard key={item.ticker} item={item} />
))}
```
to:
```tsx
{items.map((item, i) => (
  <StockCard
    key={item.ticker}
    item={item}
    animationDelay={Math.min(i, 11) * 40}
  />
))}
```

> `Math.min(i, 11) * 40` means cards 0–11 stagger at 0ms–440ms. Cards 12+ all receive 440ms, which is imperceptible by the time the page has rendered — no conditional class toggling needed.

- [ ] **Step 3: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 4: Manually verify** — switch to grid view in Screener. Cards stagger in at 40ms intervals (first 12 visibly staggered). Refresh to replay.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/screener-grid.tsx
git commit -m "feat: stagger screener grid cards on load"
```

---

## Chunk 5: Stock detail — signal cards

### Task 8: Stagger signal cards on stock detail page

**Files:**
- Modify: `frontend/src/components/signal-cards.tsx`

The current render (lines 79-88) maps over the `cards` array and renders each as a `<Card>` with:

```tsx
{cards.map((card) => {
  const sentiment = signalToSentiment(card.signal, card.type);
  return (
    <Card
      key={card.title}
      className={cn(
        "border-l-4",
        SENTIMENT_BORDER_CLASSES[sentiment]
      )}
    >
```

- [ ] **Step 1: Add `i` to the map and apply `animate-fade-slide-up` + `--stagger-delay` to each `<Card>`:**

Replace the `cards.map((card) => {` block with:

```tsx
{cards.map((card, i) => {
  const sentiment = signalToSentiment(card.signal, card.type);
  return (
    <Card
      key={card.title}
      className={cn(
        "border-l-4 animate-fade-slide-up",
        SENTIMENT_BORDER_CLASSES[sentiment]
      )}
      style={{ '--stagger-delay': `${i * 80}ms` } as React.CSSProperties}
    >
```

The stagger sequence: RSI at 0ms, MACD at 80ms, SMA at 160ms, Bollinger at 240ms.

- [ ] **Step 2: Run lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors.

- [ ] **Step 3: Manually verify** — open a stock detail page (e.g. `/stocks/AAPL`). The four signal cards (RSI, MACD, SMA, Bollinger) stagger in at 0ms, 80ms, 160ms, 240ms.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/signal-cards.tsx
git commit -m "feat: stagger signal cards on stock detail page"
```

---

## Chunk 6: Final verification

### Task 9: Full lint + build + accessibility check

- [ ] **Step 1: Run full frontend lint**

```bash
cd frontend && npm run lint
```
Expected: zero errors/warnings.

- [ ] **Step 2: Run production build**

```bash
cd frontend && npm run build
```
Expected: builds successfully with no TypeScript errors.

- [ ] **Step 3: Verify prefers-reduced-motion**

In Chrome DevTools → **Rendering tab** (open via ⋮ → More Tools → Rendering) → find "Emulate CSS media feature prefers-reduced-motion" → set to "reduce". Refresh the app. All page transitions and card animations should complete **instantly** (≤0.01ms). Confirm visually that no motion is perceptible.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: entry animations complete — fade-slide-up stagger + prefers-reduced-motion"
```
