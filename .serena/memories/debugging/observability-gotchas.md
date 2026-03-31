---
scope: project
category: debugging
updated_by: session-76
---

# Observability System Gotchas

## ObservabilityCollector outside agent pipeline is a no-op
A freshly instantiated `ObservabilityCollector()` has `_db_writer = None`. All `record_request()` / `record_tool_execution()` calls silently do nothing. The wired collector lives on `app.state` and is set up during lifespan. Code outside the agent pipeline (e.g., chat router decline paths) must call `write_event()` directly from `backend.agents.observability_writer`.

## ContextVars not set in all code paths
`current_query_id` and `current_session_id` are set in the chat router AFTER session resolution. Decline paths that fire before session resolution (input guard, injection detection) will have `None` for both. Any observability write in these paths must explicitly set `current_query_id` to a fresh UUID, or the resulting `llm_call_log` rows will have `query_id=NULL` and be invisible to `get_query_list()` (which filters `WHERE query_id IS NOT NULL`).

## record_cascade writes to llm_call_log — must include status
`ObservabilityCollector.record_cascade()` writes LLM error events. The `status` key must be explicitly set to `"error"` in the data dict — otherwise `write_event` defaults to `"completed"`, making LLM errors invisible to status filters.

## eval_results.query_id has no UNIQUE constraint
Multiple assessment runs can produce rows with the same `query_id`. Any JOIN from `llm_call_log` to `eval_results` must aggregate (GROUP BY query_id) in a subquery first, or the LEFT JOIN will fan out rows and inflate counts/costs.

## PostgreSQL GROUP BY strictness with subquery columns
When LEFT JOINing a subquery and selecting one of its columns, PostgreSQL requires it in GROUP BY or wrapped in an aggregate (e.g., `func.max()`). Even if the subquery is pre-aggregated (1 row per key), PostgreSQL doesn't know that. Use `func.max(subq.c.column)` to satisfy the constraint.
