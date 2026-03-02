---
paths:
  - "frontend/**/*.{ts,tsx}"
---
# Frontend Rules

- Use TypeScript strict mode — no `any` types
- Components use functional style with hooks, never class components
- Style with Tailwind CSS utility classes + shadcn/ui components
- Use TanStack Query (React Query) for all data fetching, never raw fetch in components
- API calls go through a centralized `lib/api.ts` wrapper with JWT auto-refresh
- Charts use Recharts library
- Keep components small and focused — extract when >150 lines
- Use Next.js App Router patterns (server components where appropriate)
