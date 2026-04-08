"""add respStmt fields to collections

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("resp", sa.String(256), nullable=True))
    op.add_column("collections", sa.Column("resp_name", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("collections", "resp_name")
    op.drop_column("collections", "resp")
