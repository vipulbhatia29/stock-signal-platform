"""023 — Auth overhaul: oauth_accounts, email_verified, deleted_at, method

Revision ID: 5c9a05c38ee1
Revises: c870473fe107
Create Date: 2026-04-01 17:54:56.402217

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c9a05c38ee1"
down_revision: Union[str, Sequence[str], None] = "c870473fe107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- oauth_accounts table ---
    op.create_table(
        "oauth_accounts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_sub", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_sub", name="uq_oauth_provider_sub"),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_user_provider"),
    )
    op.create_index(op.f("ix_oauth_accounts_user_id"), "oauth_accounts", ["user_id"], unique=False)

    # --- users table: auth overhaul columns ---
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
    )

    # Grandfather existing users as verified
    op.execute("UPDATE users SET email_verified = true, email_verified_at = NOW()")

    # --- login_attempts: method + provider_sub ---
    op.add_column(
        "login_attempts",
        sa.Column(
            "method",
            sa.String(length=20),
            server_default=sa.text("'password'"),
            nullable=False,
        ),
    )
    op.add_column("login_attempts", sa.Column("provider_sub", sa.String(length=255), nullable=True))

    # --- TECH DEBT FIX: chat_sessions FK missing ondelete CASCADE ---
    # Conditional — table may not exist in all environments
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'chat_sessions'")
    )
    if result.fetchone():
        op.drop_constraint("chat_sessions_user_id_fkey", "chat_sessions", type_="foreignkey")
        op.create_foreign_key(
            "chat_sessions_user_id_fkey",
            "chat_sessions",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Downgrade schema."""
    # --- Restore chat_sessions FK (no CASCADE) ---
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'chat_sessions'")
    )
    if result.fetchone():
        op.drop_constraint("chat_sessions_user_id_fkey", "chat_sessions", type_="foreignkey")
        op.create_foreign_key(
            "chat_sessions_user_id_fkey",
            "chat_sessions",
            "users",
            ["user_id"],
            ["id"],
        )

    # --- login_attempts ---
    op.drop_column("login_attempts", "provider_sub")
    op.drop_column("login_attempts", "method")

    # --- users ---
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")

    # --- oauth_accounts ---
    op.drop_index(op.f("ix_oauth_accounts_user_id"), table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
