"""add build_status, last_build_at, build_error to search_engines

Revision ID: 0034
Revises: 0033
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reuse the existing website_build_status PostgreSQL enum type (same values).
    build_status_enum = postgresql.ENUM(
        name="website_build_status", create_type=False
    )
    op.add_column(
        "search_engines",
        sa.Column(
            "build_status",
            build_status_enum,
            nullable=False,
            server_default="idle",
        ),
    )
    op.add_column(
        "search_engines",
        sa.Column("last_build_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "search_engines",
        sa.Column("build_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_engines", "build_error")
    op.drop_column("search_engines", "last_build_at")
    op.drop_column("search_engines", "build_status")
