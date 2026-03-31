"""021_login_attempts + pipeline_run step_durations

Revision ID: 2146d203aa47
Revises: c2d3e4f5a6b7
Create Date: 2026-03-31 14:26:46.237328

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2146d203aa47'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create login_attempts table and add step_durations to pipeline_runs."""
    # --- login_attempts table ---
    op.create_table('login_attempts',
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('user_agent', sa.String(length=500), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('failure_reason', sa.String(length=50), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_login_attempts_email'), 'login_attempts', ['email'], unique=False)
    op.create_index(
        op.f('ix_login_attempts_timestamp'), 'login_attempts', ['timestamp'], unique=False
    )

    # --- pipeline_runs: add step_durations + total_duration_seconds ---
    op.add_column(
        'pipeline_runs',
        sa.Column('step_durations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column('pipeline_runs', sa.Column('total_duration_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop login_attempts table and remove step_durations from pipeline_runs."""
    op.drop_column('pipeline_runs', 'total_duration_seconds')
    op.drop_column('pipeline_runs', 'step_durations')
    op.drop_index(op.f('ix_login_attempts_timestamp'), table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_email'), table_name='login_attempts')
    op.drop_table('login_attempts')
