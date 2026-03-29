"""017: assessment tables (eval_runs, eval_results) and log indexes.

Revision ID: a7b3c4d5e6f7
Revises: ea8da8624c85
Create Date: 2026-03-28

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "ea8da8624c85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create eval tables and add missing log indexes."""
    # --- eval_runs table ---
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("total_queries", sa.Integer, nullable=False),
        sa.Column("passed_queries", sa.Integer, nullable=False),
        sa.Column("pass_rate", sa.Float, nullable=False),
        sa.Column("total_cost_usd", sa.Float, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- eval_results table ---
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("eval_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_index", sa.Integer, nullable=False),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("intent_category", sa.String(50), nullable=False),
        sa.Column("agent_type", sa.String(50), nullable=False, server_default="react_v2"),
        # Scores
        sa.Column("tool_selection_pass", sa.Boolean, nullable=False),
        sa.Column("grounding_score", sa.Float, nullable=False),
        sa.Column("termination_pass", sa.Boolean, nullable=False),
        sa.Column("external_resilience_pass", sa.Boolean, nullable=True),
        sa.Column("reasoning_coherence_score", sa.Float, nullable=True),
        # Metadata
        sa.Column("tools_called", postgresql.JSONB, nullable=False),
        sa.Column("iteration_count", sa.Integer, nullable=False),
        sa.Column("total_cost_usd", sa.Float, nullable=False),
        sa.Column("total_duration_ms", sa.Integer, nullable=False),
        sa.Column("langfuse_trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # eval_results indexes
    op.create_index("ix_eval_results_eval_run_id", "eval_results", ["eval_run_id"])
    op.create_index("ix_eval_results_intent_category", "eval_results", ["intent_category"])

    # --- Missing log indexes (spec §12.3) ---
    op.create_index("idx_llm_call_log_created_at", "llm_call_log", [sa.text("created_at DESC")])
    op.create_index(
        "idx_tool_execution_log_created_at",
        "tool_execution_log",
        [sa.text("created_at DESC")],
    )
    op.create_index("idx_llm_call_log_query_cost", "llm_call_log", ["query_id", "cost_usd"])
    op.create_index(
        "idx_llm_call_log_created_agent",
        "llm_call_log",
        [sa.text("created_at DESC"), "agent_type"],
    )


def downgrade() -> None:
    """Drop eval tables and log indexes."""
    op.drop_index("idx_llm_call_log_created_agent", "llm_call_log")
    op.drop_index("idx_llm_call_log_query_cost", "llm_call_log")
    op.drop_index("idx_tool_execution_log_created_at", "tool_execution_log")
    op.drop_index("idx_llm_call_log_created_at", "llm_call_log")
    op.drop_index("ix_eval_results_intent_category", "eval_results")
    op.drop_index("ix_eval_results_eval_run_id", "eval_results")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
