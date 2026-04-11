"""add footer_text to search_engines

Revision ID: 0039
Revises: 0038
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_engines",
        sa.Column("footer_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_engines", "footer_text")
