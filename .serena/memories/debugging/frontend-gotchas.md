---
scope: project
category: debugging
---

# Frontend Debugging Gotchas

## ESLint react-hooks/set-state-in-effect
- Calling `setState()` synchronously inside `useEffect` body triggers this error.
- Fix: use lazy `useState(() => initialValue)` for one-time reads (e.g. localStorage).
- For reactive updates: use `MutationObserver` callback inside effect, not the effect body directly.

## Recharts colors
- CSS vars (hsl(var(--x))) do NOT resolve inside Recharts.
- Use `useChartColors()` hook (reads via `getComputedStyle`).
- For initial render: `useState(() => readCssVar('--color-positive'))` — reads synchronously on mount.

## API double-prefix
- `API_BASE = "/api/v1"` is already in `lib/api.ts`.
- Hook paths: `/portfolio/positions` NOT `/api/v1/portfolio/positions`.

## next/image
- Always `<Image />` from `next/image`, never raw `<img>`.
- Requires `width` + `height` or `fill` prop.

## Worktree subagents
- Claude Code permission model restricts Write/Bash in isolated worktrees.
- Write files from main session; use worktrees for research/read tasks only.

## JS template literals via Bash
- Python heredoc/string replacement via Bash escapes backticks in JS template literals.
- Use Edit tool or Write tool for JS/TS files with template literals.

## base-ui/shadcn v4 triggers
- `SheetTrigger`, `PopoverTrigger`, and ALL base-ui trigger components use `render={<Button />}`, NOT `asChild`.

## TypeScript strict: `unknown` in JSX
- Props typed as `unknown` cannot be used in JSX conditionals like `{value && <div/>}`.
- TypeScript evaluates `unknown && ReactElement` as `unknown | ReactElement` → not assignable to `ReactNode`.
- Fix: use `{value != null && <div/>}` — the explicit null check narrows the type.
- ESLint doesn't catch this — only `tsc --noEmit` does. Always run both locally before pushing.

## TanStack Query cache invalidation
- After mutations that update backend data (e.g., Refresh All ingest), ALL dependent query keys must be invalidated — not just the primary one. Dashboard uses ~12 query keys; invalidating only `["watchlist"]` leaves other tiles stale.
- Use `enabled` param on `useQuery` to skip unnecessary requests (e.g., `usePortfolioForecast(hasPositions)` — don't call `/forecasts/portfolio` when there are no positions).

## ESM-only packages in Jest
- `react-markdown` v9+, `rehype-highlight`, `remark-gfm` are ESM-only.
- Jest runs in CJS mode and cannot import them directly.
- Fix: add `moduleNameMapper` mocks in `jest.config.ts` pointing to CJS mock files in `__tests__/__mocks__/`.
- Mock files use `require("react")` with `// eslint-disable-next-line @typescript-eslint/no-require-imports`.
