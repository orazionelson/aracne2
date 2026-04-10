"""add custom_css and custom_js to websites

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("websites", sa.Column("custom_css", sa.Text(), nullable=True))
    op.add_column("websites", sa.Column("custom_js", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("websites", "custom_js")
    op.drop_column("websites", "custom_css")
