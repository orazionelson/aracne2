"""add objectdesc_form field to collections

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("objectdesc_form", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "objectdesc_form")
