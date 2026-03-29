# Local LLM Triage — Mandatory Before Every Implementation Task

Before starting ANY implementation task (including subagent-dispatched tasks):

1. Score the task: `context_span + convention_density + ambiguity` (each 1-5)
2. If total <= 8: MUST present to user:
   "This scores X/15 — suitable for `/implement-local`. Delegate to local LLM? (y/n)"
3. WAIT for the user's answer before proceeding
4. If user says yes: use `/implement-local` skill
5. If user says no or LM Studio is not running: proceed with Opus

## No Exceptions

- Parallel subagent dispatch does NOT exempt tasks from triage
- Pre-scored tasks in plans still require presenting the choice
- "Speed" is NOT a valid reason to skip
- Batch triage is acceptable: present all eligible tasks at once, let user decide which go local
