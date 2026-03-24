---
scope: project
category: project
---

# UI Polish Phase — Lovable vs Current App Comparison

## Status: PLANNED (deferred — user will initiate)

## Context
Session 51: User identified significant UI quality gap between the current app and the Lovable prototype. Decided to defer to a dedicated phase rather than quick-fix.

## Lovable Prototype
- URL: https://lovable.dev/projects/00bdab20-3148-4613-85ee-a4b61752b43c
- Gap analysis doc: `docs/lovable/migration-gap-analysis.md`
- Workflow doc: `docs/superpowers/plans/2026-03-19-ui-migration-workflow.md`

## Known Issues (from Session 51 screenshots)
1. **DialogTrigger crash** — `ScorecardModal` (scorecard-modal.tsx:136) uses DialogTrigger with non-native button. base-ui/shadcn v4 `render` prop issue.
2. **Font inconsistency** — ticker names (SNDK) vs values ($0.00) use different weight/style. Section labels (PORTFOLIO VALUE, UNREALIZED P&L) are barely readable.
3. **Signals panel floating** — not aligned with dashboard grid, looks disconnected.
4. **Stale analyze_stock banner** — tool call result leaking into dashboard UI at top.
5. **Overall cohesion** — lacks premium financial UI feel that Lovable prototype has.

## Approach (user-approved)
- Use `frontend-design` skill for production-grade UI
- Page-by-page comparison: Lovable vs current app
- Multiple phases, review each pass before proceeding
- Pages to cover: Dashboard, Screener, Stock Detail, Portfolio, Sectors, Auth, Chat

## How to apply
When user initiates this work, start by:
1. Read this memory + `architecture/frontend-design-system`
2. Open Lovable prototype and take screenshots for comparison
3. Create a gap analysis per page
4. Propose phases with JIRA stories
5. Implement page-by-page with user review between passes
