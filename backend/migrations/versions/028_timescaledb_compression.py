"""028_timescaledb_compression

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-04-13 20:00:00.000000

Enable TimescaleDB compression on stock_prices, signal_snapshots, news_articles.

Thresholds chosen to avoid conflicts with existing upsert/update patterns:
- stock_prices: 180d (upserts only touch recent data during nightly refresh)
- signal_snapshots: 180d (daily signal computation only writes today's snapshot)
- news_articles: 60d (scored_at UPDATE runs within hours of ingestion;
  retention purge uses drop_chunks at 90d, so chunks are compressed
  at 60d and dropped at 90d — gives 30d of compression savings)
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMPRESSION_CONFIG = [
    {
        "table": "stock_prices",
        "segmentby": "ticker",
        "orderby": "time DESC",
        "policy_interval": "180 days",
    },
    {
        "table": "signal_snapshots",
        "segmentby": "ticker",
        "orderby": "computed_at DESC",
        "policy_interval": "180 days",
    },
    {
        "table": "news_articles",
        "segmentby": "ticker",
        "orderby": "published_at DESC",
        "policy_interval": "60 days",
    },
]


def upgrade() -> None:
    for cfg in COMPRESSION_CONFIG:
        table = cfg["table"]
        orderby = cfg["orderby"]
        segmentby = cfg["segmentby"]
        interval = cfg["policy_interval"]

        # Build ALTER TABLE SET with compression settings
        compress_opts = f"timescaledb.compress_orderby = '{orderby}'"
        if segmentby:
            compress_opts += f", timescaledb.compress_segmentby = '{segmentby}'"

        op.execute(f"ALTER TABLE {table} SET (timescaledb.compress, {compress_opts})")
        op.execute(f"SELECT add_compression_policy('{table}', INTERVAL '{interval}')")


def downgrade() -> None:
    for cfg in reversed(COMPRESSION_CONFIG):
        table = cfg["table"]

        # 1. Remove the automatic compression policy
        op.execute(f"SELECT remove_compression_policy('{table}', if_exists => true)")

        # 2. Decompress any already-compressed chunks
        op.execute(f"""
            DO $$
            DECLARE chunk regclass;
            BEGIN
                FOR chunk IN
                    SELECT format('%I.%I', chunk_schema, chunk_name)::regclass
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = '{table}' AND is_compressed
                LOOP
                    PERFORM decompress_chunk(chunk);
                END LOOP;
            END $$;
        """)

        # 3. Disable compression on the hypertable
        op.execute(f"ALTER TABLE {table} SET (timescaledb.compress = false)")
