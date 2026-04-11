"""add page_bg_color, header_bg_color, header_hidden to search_engines

Revision ID: 0038
Revises: 0037
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_engines",
        sa.Column("page_bg_color", sa.String(7), nullable=True),
    )
    op.add_column(
        "search_engines",
        sa.Column("header_bg_color", sa.String(7), nullable=True),
    )
    op.add_column(
        "search_engines",
        sa.Column(
            "header_hidden",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("search_engines", "header_hidden")
    op.drop_column("search_engines", "header_bg_color")
    op.drop_column("search_engines", "page_bg_color")
