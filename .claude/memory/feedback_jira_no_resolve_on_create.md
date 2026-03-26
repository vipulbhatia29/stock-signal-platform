---
name: feedback_jira_no_resolve_on_create
description: Never transition JIRA tickets to Done when only creating them — only resolve after implementation is complete
type: feedback
---

Do NOT transition JIRA tickets to Done (or any resolved state) when creating them as backlog items.
Only transition tickets when the actual implementation work is complete and merged.

**Why:** Session 57 — accidentally resolved KAN-162 (Langfuse Integration) immediately after creating it as a backlog item. User caught it.

**How to apply:** When creating JIRA tickets for future/backlog work, leave them in "To Do" status. Only transition to Done after the code is shipped and PR merged.
