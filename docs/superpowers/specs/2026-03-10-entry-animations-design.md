# Entry Animations + prefers-reduced-motion — Design Spec

**Date:** 2026-03-10
**Status:** Approved

## Goal

Add tasteful, staggered entry animations to the stock signal platform frontend — cards slide up and fade in as they appear, with full `prefers-reduced-motion` support that collapses all motion to instant.

## Animation Feel

**B — Moderate (Robinhood-style):** Fade + gentle slide up (10px). Staggered per element. Matches the Bloomberg-inspired dark theme without being distracting.

## Animation System

### Keyframes (added to `globals.css`)

- `fade-in` — opacity 0→1, 400ms ease. Used for page transitions and charts.
- `fade-slide-up` — opacity 0→1 + translateY(10px→0), 400ms cubic-bezier(.22,.68,0,1.2). Used for all cards and table rows.

### Stagger mechanism

Pure CSS via `--stagger-delay` custom property set as inline style on each element:

```tsx
style={{ '--stagger-delay': `${i * 60}ms` } as React.CSSProperties}
```

The Tailwind class reads it:
```css
.animate-fade-slide-up {
  animation: fade-slide-up 0.4s cubic-bezier(.22,.68,0,1.2) var(--stagger-delay, 0ms) both;
}
```

### `prefers-reduced-motion` handling

One global rule in `globals.css` collapses all animations to near-instant. No per-component logic needed:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-delay: 0ms !important;
  }
}
```

## Animated Elements

| Element | Component file | Animation | Stagger |
|---|---|---|---|
| Page (route change) | `app/(authenticated)/layout.tsx` | `fade-in` on wrapper keyed by pathname | none |
| Index cards (3) | `components/index-card.tsx` + dashboard page | `fade-slide-up` | 0 / 80 / 160ms |
| Watchlist stock cards | `components/stock-card.tsx` + dashboard page | `fade-slide-up` | 60ms × index, capped at 8 |
| Screener table rows | `components/screener-table.tsx` | `fade-slide-up` | 30ms × index, first 12 rows only |
| Screener grid cards | `components/screener-grid.tsx` | `fade-slide-up` | 40ms × index, first 12 cards only |
| Signal cards (4) | `components/signal-cards.tsx` | `fade-slide-up` | 0 / 80 / 160 / 240ms |

## Out of Scope

- Metric cards (risk/return) — signal cards already animate on that page; double stagger feels cluttered
- Chart fade-in — charts are behind loading skeletons; adding another animation layer is redundant
- Hover/interaction animations — separate concern
- Exit animations — not needed for this phase

## Files Changed

| File | Change |
|---|---|
| `frontend/src/app/globals.css` | Add keyframes + Tailwind class definitions + `prefers-reduced-motion` rule |
| `frontend/src/app/(authenticated)/layout.tsx` | Add `animate-fade-in` to `<main>` element (no `usePathname`, no `key` prop — CSS replays naturally on each page render) |
| `frontend/src/app/(authenticated)/dashboard/page.tsx` | Pass stagger index to index cards + stock cards |
| `frontend/src/components/index-card.tsx` | Accept `animationDelay` prop, apply `animate-fade-slide-up` |
| `frontend/src/components/stock-card.tsx` | Accept `animationDelay` prop, apply `animate-fade-slide-up` |
| `frontend/src/components/screener-table.tsx` | Apply `animate-fade-slide-up` to first 12 rows with stagger |
| `frontend/src/components/screener-grid.tsx` | Apply `animate-fade-slide-up` to first 12 cards with stagger |
| `frontend/src/components/signal-cards.tsx` | Apply `animate-fade-slide-up` with 80ms stagger per card |
