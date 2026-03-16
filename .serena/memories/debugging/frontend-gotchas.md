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
