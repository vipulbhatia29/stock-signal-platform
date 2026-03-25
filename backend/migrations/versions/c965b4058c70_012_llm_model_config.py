"""012_llm_model_config

Create llm_model_config table for data-driven LLM cascade.

Revision ID: c965b4058c70
Revises: d68e82e90c96
Create Date: 2026-03-25 15:10:34.676807

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c965b4058c70"
down_revision: Union[str, Sequence[str], None] = "d68e82e90c96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create llm_model_config table and seed cascade data."""
    op.create_table(
        "llm_model_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("tpm_limit", sa.Integer(), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("tpd_limit", sa.Integer(), nullable=True),
        sa.Column("rpd_limit", sa.Integer(), nullable=True),
        sa.Column("cost_per_1k_input", sa.Numeric(10, 6), server_default="0"),
        sa.Column("cost_per_1k_output", sa.Numeric(10, 6), server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_name", "tier", name="uq_provider_model_tier"),
    )

    # Seed: Planner tier
    op.execute(
        """
        INSERT INTO llm_model_config
            (provider, model_name, tier, priority,
             tpm_limit, rpm_limit, tpd_limit, rpd_limit, notes)
        VALUES
            ('groq', 'llama-3.3-70b-versatile', 'planner', 1, 12000, 30, 100000, 1000,
             'Best tool-calling, strong JSON'),
            ('groq', 'moonshotai/kimi-k2-instruct', 'planner', 2, 10000, 60, 300000, 1000,
             'Good reasoning for complex plans'),
            ('groq', 'meta-llama/llama-4-scout-17b-16e-instruct',
             'planner', 3, 30000, 30, 500000, 1000,
             'Fast, generous TPM fallback'),
            ('anthropic', 'claude-sonnet-4-6', 'planner', 4, NULL, NULL, NULL, NULL,
             'Paid fallback'),
            ('openai', 'gpt-4o', 'planner', 5, NULL, NULL, NULL, NULL,
             'Last-resort fallback')
    """
    )

    # Seed: Synthesizer tier
    op.execute(
        """
        INSERT INTO llm_model_config
            (provider, model_name, tier, priority,
             tpm_limit, rpm_limit, tpd_limit, rpd_limit, notes)
        VALUES
            ('groq', 'openai/gpt-oss-120b', 'synthesizer', 1, 8000, 30, 200000, 1000,
             'Highest quality free model'),
            ('groq', 'moonshotai/kimi-k2-instruct', 'synthesizer', 2, 10000, 60, 300000, 1000,
             'Strong reasoning fallback'),
            ('anthropic', 'claude-sonnet-4-6', 'synthesizer', 3, NULL, NULL, NULL, NULL,
             'Quality guarantee'),
            ('openai', 'gpt-4o', 'synthesizer', 4, NULL, NULL, NULL, NULL,
             'Last-resort fallback')
    """
    )


def downgrade() -> None:
    """Drop llm_model_config table."""
    op.drop_table("llm_model_config")
