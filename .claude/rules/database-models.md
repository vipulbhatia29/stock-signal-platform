---
paths:
  - "backend/models/**/*.py"
---
# Database Model Rules

- Use SQLAlchemy 2.0 declarative style with mapped_column()
- Every model inherits from a shared Base class defined in backend/database.py
- Use TimescaleDB hypertables for time-series data (stock prices, signal history)
- Always include created_at and updated_at timestamps
- Use UUID primary keys for user-facing models
- Add __repr__ for debugging
- After creating/modifying a model, generate an Alembic migration:
  `uv run alembic revision --autogenerate -m "description"`
- Then apply it: `uv run alembic upgrade head`
- Then verify with: `uv run alembic current`
- REFER TO `docs/data-architecture.md` for the complete entity model,
  TimescaleDB configuration, and compression policies
- Time-series tables (StockPrice, SignalSnapshot, FundamentalSnapshot,
  ForecastResult, MacroSnapshot) are APPEND-ONLY — never update historical rows
- Every ForecastResult MUST have a model_version_id FK to ModelVersion —
  predictions without lineage are useless
- ModelVersion tracks: model_type, version, training data range,
  hyperparameters (JSONB), metrics (JSONB), artifact_path, is_active
- Only one ModelVersion can be is_active=True per (model_type, ticker) pair
