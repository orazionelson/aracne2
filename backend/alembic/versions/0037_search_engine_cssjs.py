"""add custom_css, custom_js, include_jquery to search_engines

Revision ID: 0037
Revises: 0036
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_engines", sa.Column("custom_css", sa.Text(), nullable=True))
    op.add_column("search_engines", sa.Column("custom_js", sa.Text(), nullable=True))
    op.add_column(
        "search_engines",
        sa.Column(
            "include_jquery",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("search_engines", "include_jquery")
    op.drop_column("search_engines", "custom_js")
    op.drop_column("search_engines", "custom_css")
