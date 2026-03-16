---
scope: project
category: architecture
---

# TimescaleDB Patterns

## Hypertables
- All time-series tables (price_data, signals, etc.) are hypertables.
- Partition column is always `time` (timestamptz).
- PK is composite: `(id, time)` — required for hypertable partitioning.

## Upsert Pattern
  stmt = insert(PriceData).values(rows)
  stmt = stmt.on_conflict_do_update(
      constraint="price_data_pkey",   # named constraint, NOT index_elements
      set_={"open": stmt.excluded.open, ...}
  )
  await session.execute(stmt)

Note: ON CONFLICT needs the named constraint, not column list — because PK is composite.

## Alembic Caution
Alembic autogenerate FALSELY detects TimescaleDB internal indexes as user-created.
Always review `alembic revision --autogenerate` output — manually remove any `op.drop_index()`
calls that reference TimescaleDB-managed indexes (pattern: `_compressed_hypertable_*`).

## Continuous Aggregates
Currently using nightly Celery jobs instead of continuous aggregates (simpler).
If performance degrades, revisit continuous aggregates for signals pre-computation.
