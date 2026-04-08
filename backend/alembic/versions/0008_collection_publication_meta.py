"""add publication metadata fields to collections

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("publisher", sa.String(256), nullable=True))
    op.add_column("collections", sa.Column("pub_place", sa.String(256), nullable=True))
    op.add_column("collections", sa.Column("pub_year", sa.SmallInteger(), nullable=True))
    op.add_column(
        "collections",
        sa.Column(
            "license_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("licenses.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "license_id")
    op.drop_column("collections", "pub_year")
    op.drop_column("collections", "pub_place")
    op.drop_column("collections", "publisher")
