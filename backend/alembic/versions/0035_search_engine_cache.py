"""add cache_ttl_minutes to search_engines and create search_engine_query_cache

Revision ID: 0035
Revises: 0034
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cache TTL per search engine (0 = disabled).
    op.add_column(
        "search_engines",
        sa.Column(
            "cache_ttl_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )

    op.create_table(
        "search_engine_query_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "search_engine_id",
            UUID(as_uuid=True),
            sa.ForeignKey("search_engines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("query_text", sa.String(512), nullable=False),
        sa.Column("collections_key", sa.String(512), nullable=False),
        sa.Column("hits", JSONB, nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_se_query_cache_engine_id",
        "search_engine_query_cache",
        ["search_engine_id"],
    )
    op.create_index(
        "ix_se_query_cache_engine_hash",
        "search_engine_query_cache",
        ["search_engine_id", "query_hash"],
        unique=True,
    )
    op.create_index(
        "ix_se_query_cache_expires_at",
        "search_engine_query_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_table("search_engine_query_cache")
    op.drop_column("search_engines", "cache_ttl_minutes")
