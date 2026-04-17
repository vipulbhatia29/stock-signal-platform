"""Observability schema foundation (Obs 1a PR1).

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS observability"))
    op.create_table(
        "schema_versions",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        schema="observability",
    )
    op.execute(
        sa.text(
            "INSERT INTO observability.schema_versions (version, notes) "
            "VALUES ('v1', 'Obs 1a PR1 — initial event contract (ObsEventBase)')"
        )
    )


def downgrade() -> None:
    op.drop_table("schema_versions", schema="observability")
    op.execute(sa.text("DROP SCHEMA IF EXISTS observability"))
