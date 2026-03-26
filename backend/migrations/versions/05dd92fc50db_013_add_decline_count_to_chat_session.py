"""013_add_decline_count_to_chat_session

Revision ID: 05dd92fc50db
Revises: c965b4058c70
Create Date: 2026-03-25 21:45:24.505900

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "05dd92fc50db"
down_revision: Union[str, Sequence[str], None] = "c965b4058c70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_session",
        sa.Column("decline_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_session", "decline_count")
