# Frontend

Next.js application with TypeScript, Tailwind CSS, shadcn/ui, and Recharts.

## Key Patterns

- App Router (not Pages Router) — all routes in `app/` directory
- `lib/api.ts` wraps fetch with JWT auto-refresh and error handling
- `lib/auth.ts` manages token storage and refresh logic
- `hooks/` contains custom hooks for auth, chat, data fetching
- All data fetching uses TanStack Query — never raw fetch in components
- Charts use Recharts — import from `recharts`
- UI primitives from shadcn/ui — install with `npx shadcn@latest add <component>`

## Commands

```bash
npm run dev          # Start dev server (port 3000)
npm run build        # Production build
npm run lint         # ESLint
npx tsc --noEmit     # Type check
npx jest             # Unit tests (jsdom env)
```

## Important

- Backend API runs on port 8181: `NEXT_PUBLIC_API_URL=http://localhost:8181`
- This is a SINGLE app — no iframes, no embedded services
- Jest needs `testEnvironment: "jsdom"` (not `"node"`)
- Tailwind v4: use `font-family: var(--font-sora)` in `@layer base`, not `@theme`
- `types/api.ts` has ~115 exported types — single source of truth for all backend schema types
- Popover/Trigger components use `@base-ui/react` (NOT shadcn) — use `render` prop, NOT `asChild`
- 8 route groups: dashboard, screener, portfolio, stocks, sectors, observability, admin, chat
- 68 components in `src/components/`, 12 hooks in `src/hooks/`
- New hooks: `usePortfolioAnalytics()`, `useStockAnalytics()` (QuantStats data from nightly pipeline)
- `API_BASE = "/api/v1"` in `api.ts` — hooks use `/portfolio/...` NOT `/api/v1/portfolio/...` (double-prefix bug)
