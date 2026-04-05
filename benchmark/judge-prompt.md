You are an expert code reviewer evaluating {impl_count} implementations of the same coding task.
Score each INDEPENDENTLY on the rubric below. Do not let one implementation bias your scoring of another.

## Task
{task_description}

## Project Conventions (relevant excerpt)
- Python: async by default, type hints required, no str(e) in user-facing output
- Tests: pytest (not unittest), factory-boy for fixtures, bare functions not classes
- DB: SQLAlchemy async, Alembic migrations must not drop TimescaleDB indexes
- Naming: snake_case for Python, kebab-case for URLs, PascalCase for models/schemas
- Error handling: log real error, return safe generic message

## Scoring Rubric
{rubric_yaml}

{implementations_block}

Respond in JSON ONLY. No markdown fences. No preamble. No explanation outside JSON.

{scoring_json_schema}
