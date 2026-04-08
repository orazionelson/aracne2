"""replace resp/resp_name scalar columns with resp_stmts JSONB array

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("collections", "resp")
    op.drop_column("collections", "resp_name")
    op.add_column("collections", sa.Column("resp_stmts", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("collections", "resp_stmts")
    op.add_column("collections", sa.Column("resp_name", sa.String(256), nullable=True))
    op.add_column("collections", sa.Column("resp", sa.String(256), nullable=True))
