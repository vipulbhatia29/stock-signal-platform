---
description: Doc-delta tracking — note documentation changes needed after each sprint for batch application at phase end
paths:
  - "backend/routers/**"
  - "backend/models/**"
  - "backend/services/**"
---

# Doc-Delta Tracking

After completing each sprint or task batch during implementation, note what changed that affects documentation.

## What to Track

| Change Type | Example | Target Doc |
|------------|---------|------------|
| New endpoint | `POST /api/v1/convergence/forecast` | docs/TDD.md |
| New model | `ConvergenceScore` | docs/TDD.md |
| New service | `ConvergenceService` | docs/TDD.md |
| New user-facing feature | Convergence scoring dashboard | docs/FSD.md (add FR-XX) |
| Product scope change | Added forecast intelligence | docs/PRD.md |
| Feature description | New dashboard section | README.md |

## Storage Format

Store deltas in Serena memory key `session/doc-delta` using this format:

```
## Doc Delta Log

### Sprint N
- [endpoint] POST /api/v1/convergence/forecast — backend/routers/convergence.py
- [model] ConvergenceScore — backend/models/convergence.py
- [FR] FR-42: Convergence scoring — needs update in FSD
```

## Workflow

After each sprint completion:
1. Review what was built (scan commits, new files)
2. Note deltas in the format above
3. Append to existing `session/doc-delta` memory (don't overwrite previous sprints)
4. Present: "Sprint done. Doc delta: [summary]. Apply now or accumulate?"

Deltas are accumulated across sprints and applied in batch at phase end via `/phase-closeout`.

Do NOT update TDD/FSD/README/PRD mid-phase — accumulate and batch.
