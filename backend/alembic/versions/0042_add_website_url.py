"""add website_url to websites

Revision ID: 0042
Revises: 0041
Create Date: 2026-04-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "websites",
        sa.Column("website_url", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("websites", "website_url")
