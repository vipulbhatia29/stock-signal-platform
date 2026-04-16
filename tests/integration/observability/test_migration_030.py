import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_observability_schema_and_seed(db_session):
    schema = (
        await db_session.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata"
                " WHERE schema_name = 'observability'"
            )
        )
    ).scalar()
    assert schema == "observability"

    cols = {
        r[0]
        for r in (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='observability' AND table_name='schema_versions'"
                )
            )
        ).all()
    }
    assert {"version", "applied_at", "notes"}.issubset(cols)

    seeded = (
        await db_session.execute(
            text(
                "SELECT version FROM observability.schema_versions ORDER BY applied_at DESC LIMIT 1"
            )
        )
    ).scalar()
    assert seeded == "v1"
