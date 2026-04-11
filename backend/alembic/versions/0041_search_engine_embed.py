"""add embed support to search_engines

Revision ID: 0041
Revises: 0040
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── A. Colonne su search_engines ──────────────────────────────────────────
    op.add_column(
        "search_engines",
        sa.Column("embed_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "search_engines",
        sa.Column("embed_config", JSONB(), nullable=False, server_default="{}"),
    )

    # ── B. Tabella search_engine_embed_logs ───────────────────────────────────
    op.create_table(
        "search_engine_embed_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "search_engine_id",
            UUID(as_uuid=True),
            sa.ForeignKey("search_engines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(512), nullable=True),
        sa.Column("referer", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("query", sa.String(512), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_embed_log_engine_time",
        "search_engine_embed_logs",
        ["search_engine_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_embed_log_engine_time", table_name="search_engine_embed_logs")
    op.drop_table("search_engine_embed_logs")
    op.drop_column("search_engines", "embed_config")
    op.drop_column("search_engines", "embed_enabled")
