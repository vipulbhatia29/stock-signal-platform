"""010 agent v2 feedback tier query_id

Revision ID: ac5d765112d6
Revises: 4bd056089124
Create Date: 2026-03-20 18:31:56.527862

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac5d765112d6"
down_revision: Union[str, Sequence[str], None] = "4bd056089124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add feedback to chat_message, tier+query_id to logs."""
    # ChatMessage: feedback column
    op.add_column("chat_message", sa.Column("feedback", sa.String(length=10), nullable=True))

    # LLMCallLog: tier + query_id
    op.add_column("llm_call_log", sa.Column("tier", sa.String(length=20), nullable=True))
    op.add_column(
        "llm_call_log",
        sa.Column("query_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_llm_call_log_query_id", "llm_call_log", ["query_id"])

    # ToolExecutionLog: query_id
    op.add_column(
        "tool_execution_log",
        sa.Column("query_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_tool_execution_log_query_id", "tool_execution_log", ["query_id"])


def downgrade() -> None:
    """Remove feedback, tier, query_id columns."""
    op.drop_index("ix_tool_execution_log_query_id", table_name="tool_execution_log")
    op.drop_column("tool_execution_log", "query_id")

    op.drop_index("ix_llm_call_log_query_id", table_name="llm_call_log")
    op.drop_column("llm_call_log", "query_id")
    op.drop_column("llm_call_log", "tier")

    op.drop_column("chat_message", "feedback")
