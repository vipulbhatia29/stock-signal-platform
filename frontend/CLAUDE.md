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

## Important

- Backend API runs on port 8181: `NEXT_PUBLIC_API_URL=http://localhost:8181`
- This is a SINGLE app — no iframes, no embedded services
- Use `npm run dev` to start (port 3000)
