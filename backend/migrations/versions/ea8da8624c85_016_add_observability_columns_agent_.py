"""016_add_observability_columns_agent_type_instance_loop_step

Add agent_type, agent_instance_id, loop_step to llm_call_log and
tool_execution_log for observability completeness (KAN-190).
agent_instance_id and loop_step are forward-compatible for Phase 8B/9A.

Revision ID: ea8da8624c85
Revises: 758e69475884
Create Date: 2026-03-27 13:01:46.229847

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "ea8da8624c85"
down_revision: Union[str, Sequence[str], None] = "758e69475884"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add observability columns to both log hypertables."""
    # llm_call_log
    op.add_column("llm_call_log", sa.Column("agent_type", sa.String(20), nullable=True))
    op.add_column(
        "llm_call_log",
        sa.Column("agent_instance_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column("llm_call_log", sa.Column("loop_step", sa.Integer(), nullable=True))
    op.create_index("ix_llm_call_log_agent_type", "llm_call_log", ["agent_type"])

    # tool_execution_log
    op.add_column("tool_execution_log", sa.Column("agent_type", sa.String(20), nullable=True))
    op.add_column(
        "tool_execution_log",
        sa.Column("agent_instance_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column("tool_execution_log", sa.Column("loop_step", sa.Integer(), nullable=True))
    op.create_index("ix_tool_execution_log_agent_type", "tool_execution_log", ["agent_type"])


def downgrade() -> None:
    """Remove observability columns from both log hypertables."""
    op.drop_index("ix_tool_execution_log_agent_type", table_name="tool_execution_log")
    op.drop_column("tool_execution_log", "loop_step")
    op.drop_column("tool_execution_log", "agent_instance_id")
    op.drop_column("tool_execution_log", "agent_type")

    op.drop_index("ix_llm_call_log_agent_type", table_name="llm_call_log")
    op.drop_column("llm_call_log", "loop_step")
    op.drop_column("llm_call_log", "agent_instance_id")
    op.drop_column("llm_call_log", "agent_type")
