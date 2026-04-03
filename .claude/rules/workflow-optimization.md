---
description: General workflow optimization rules — spec review rounds, cross-sprint review, JIRA transitions
---

# Workflow Optimization Rules

## Spec Review: One Round, Not Three

When running spec or code review (including via `superpowers:requesting-code-review`):
- Run exactly ONE review round with 5 personas
- Personas are auto-selected by domain:
  - Forecast/signals → quantitative analyst
  - Auth/security → security engineer
  - Frontend/UI → UX engineer
  - Data/models → data engineer
  - API/endpoints → API design expert
- Before starting: "I'll run a 5-persona review. Want to adjust personas or add a round?"

Do NOT run multiple escalating rounds. One round catches 95% of issues.

## No Cross-Sprint Review

Do NOT run a separate review between sprints during implementation.
Instead, at phase end, the phase-end review includes "cross-sprint integration" as an explicit dimension.

After the last sprint in a phase: "Ready for phase-end review. Skip or proceed?"

## JIRA Transition Reminder at PR Creation

When creating a PR (including via `/ship`):
1. Scan the branch name and commit messages for KAN-XXX patterns
2. Present the list of tickets that should transition: "PR ships KAN-384, KAN-385. Transition to Done? (y/n)"
3. Do NOT auto-transition — always wait for explicit approval
