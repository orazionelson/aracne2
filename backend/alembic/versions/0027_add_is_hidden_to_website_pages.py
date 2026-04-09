"""Add is_hidden to website_pages.

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "website_pages",
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            nullable=False,
            server_default="FALSE",
        ),
    )


def downgrade() -> None:
    op.drop_column("website_pages", "is_hidden")
