---
description: Local LLM triage — mandatory scoring before every implementation task
---

# Local LLM Triage — No Exceptions

The scoring formula and threshold are in CLAUDE.md Session Start #8. This rule adds enforcement clarifications.

## No Exceptions

- Parallel subagent dispatch does NOT exempt tasks from triage
- Pre-scored tasks in plans still require presenting the choice
- "Speed" is NOT a valid reason to skip
- Batch triage is acceptable: present all eligible tasks at once, let user decide which go local
- If total ≤ 8: MUST present to user and WAIT for answer before proceeding
- If user says yes: use `/implement-local` skill
- If user says no or local LLM is not running: proceed with Opus
