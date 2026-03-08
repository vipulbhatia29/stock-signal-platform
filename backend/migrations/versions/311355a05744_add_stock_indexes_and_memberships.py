"""add stock indexes and memberships

Revision ID: 311355a05744
Revises: 001_initial
Create Date: 2026-03-07 23:15:01.693386

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '311355a05744'
down_revision: Union[str, Sequence[str], None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stock_indexes',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('slug', sa.String(length=50), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_stock_indexes_slug'), 'stock_indexes', ['slug'], unique=True)
    op.create_table('stock_index_memberships',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('ticker', sa.String(length=10), nullable=False),
    sa.Column('index_id', sa.Uuid(), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['index_id'], ['stock_indexes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ticker'], ['stocks.ticker'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ticker', 'index_id', name='uq_ticker_index')
    )
    op.create_index(op.f('ix_stock_index_memberships_index_id'), 'stock_index_memberships', ['index_id'], unique=False)
    op.create_index(op.f('ix_stock_index_memberships_ticker'), 'stock_index_memberships', ['ticker'], unique=False)
    # NOTE: Alembic autogenerate falsely detects TimescaleDB-managed indexes as removed.
    # Do NOT drop them — they are created by create_hypertable() in migration 001.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_stock_index_memberships_ticker'), table_name='stock_index_memberships')
    op.drop_index(op.f('ix_stock_index_memberships_index_id'), table_name='stock_index_memberships')
    op.drop_table('stock_index_memberships')
    op.drop_index(op.f('ix_stock_indexes_slug'), table_name='stock_indexes')
    op.drop_table('stock_indexes')
