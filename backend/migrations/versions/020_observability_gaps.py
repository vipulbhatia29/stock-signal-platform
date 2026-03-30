"""020 — Observability API gaps: status, langfuse_trace_id, summaries, eval query_id.

Revision ID: c2d3e4f5a6b7
Revises: b8f9d0e1f2a3
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c2d3e4f5a6b7"
down_revision = "b8f9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add observability columns."""
    op.add_column(
        "llm_call_log",
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
    )
    op.add_column(
        "llm_call_log",
        sa.Column("langfuse_trace_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tool_execution_log",
        sa.Column("input_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "tool_execution_log",
        sa.Column("output_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "eval_results",
        sa.Column("query_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_eval_results_query_id", "eval_results", ["query_id"])


def downgrade() -> None:
    """Remove observability columns."""
    op.drop_index("ix_eval_results_query_id", table_name="eval_results")
    op.drop_column("eval_results", "query_id")
    op.drop_column("tool_execution_log", "output_summary")
    op.drop_column("tool_execution_log", "input_summary")
    op.drop_column("llm_call_log", "langfuse_trace_id")
    op.drop_column("llm_call_log", "status")
