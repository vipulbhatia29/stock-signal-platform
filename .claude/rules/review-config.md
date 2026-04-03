---
description: Review round control — default 1 round, domain-auto-selected personas
---

# Review Configuration

When `superpowers:requesting-code-review` is invoked:

## Round Control
- Default to **1 review round** (not 3)
- Only add a second round if the first round found Critical-severity issues
- Before starting: "Running 1-round, 5-persona review. Add a round?"

## Persona Auto-Selection

Select 5 personas based on the domain of the code being reviewed:

| Code Domain | Persona Pool |
|-------------|-------------|
| Forecast/signals/convergence | Quantitative Analyst, Data Scientist, Performance Engineer, API Designer, Security Engineer |
| Auth/security/JWT | Security Engineer, Cryptography Expert, API Designer, Frontend Engineer, DevOps Engineer |
| Frontend/UI/components | UX Engineer, Accessibility Expert, Performance Engineer, Frontend Architect, Security Engineer |
| Data/models/migrations | Data Engineer, DBA, API Designer, Security Engineer, Performance Engineer |
| API/endpoints/routers | API Designer, Security Engineer, Performance Engineer, Data Engineer, Frontend Consumer |
| Infrastructure/CI/Docker | DevOps Engineer, Security Engineer, Performance Engineer, Reliability Engineer, Platform Engineer |

If the code spans multiple domains, pick the top 5 most relevant personas across domains (no duplicates).
