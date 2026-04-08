"""add msidentifier_idno field to collections

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("msidentifier_idno", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "msidentifier_idno")
