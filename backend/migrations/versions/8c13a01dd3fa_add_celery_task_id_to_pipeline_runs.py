"""add celery_task_id to pipeline_runs

Revision ID: 8c13a01dd3fa
Revises: e1f2a3b4c5d6
Create Date: 2026-04-11 17:01:36.412370

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c13a01dd3fa"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add celery_task_id column + index to pipeline_runs.

    Celery preserves task.request.id across retries. Storing it gives
    dashboards a natural GROUP BY key for retry aggregation.
    """
    op.add_column(
        "pipeline_runs",
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_pipeline_runs_celery_task_id"),
        "pipeline_runs",
        ["celery_task_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove celery_task_id column + index from pipeline_runs."""
    op.drop_index(
        op.f("ix_pipeline_runs_celery_task_id"),
        table_name="pipeline_runs",
    )
    op.drop_column("pipeline_runs", "celery_task_id")
