"""add identifier_url to collections

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("identifier_url", sa.String(2048), nullable=True, default=None),
    )


def downgrade() -> None:
    op.drop_column("collections", "identifier_url")
