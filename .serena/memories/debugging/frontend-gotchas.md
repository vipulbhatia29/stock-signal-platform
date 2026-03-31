---
scope: project
category: debugging
updated_by: session-77
---

# Frontend Gotchas

- ESLint `react-hooks/set-state-in-effect`: use lazy `useState(() => ...)` or inner/outer component split with `key` remount
- Recharts needs literal color strings — use `useChartColors()`
- localStorage: lazy initializer with SSR guard
- base-ui/shadcn v4: `SheetTrigger`, `PopoverTrigger` use `render={<Button />}` prop, NOT `asChild`
- **Tailwind v4 `@theme` + Next.js fonts:** use `font-family: var(--font-sora)` directly in `@layer base`
- **composite_score scale:** API returns 0-10 (NOT 0-1). Never multiply by 10 on frontend.
- **`Date.now()` in React render:** ESLint react-compiler flags as impure. Wrap in `useMemo(() => ..., [deps])`.
- **Design system has no `--pdim` (purple dim) token.** For LLM type tags, use `bg-card2 text-[var(--chart-3)]`.
- **Falsy param checks drop valid 0/empty values:** Always use `!= null` for optional URL params in hooks.
- **Inline table expansion: each row must own its own hook call.** Shared `useQueryDetail` at table level causes stale data flash when switching rows.
- **Frontend has no role info without `/auth/me`:** JWT doesn't embed role. Must add a profile endpoint for any role-aware rendering.