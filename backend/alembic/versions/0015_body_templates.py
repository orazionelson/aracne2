"""create body_templates table

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "body_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(128), nullable=False, unique=True),
        sa.Column("snippet", sa.Text, nullable=False),
        sa.Column(
            "is_native", sa.Boolean, nullable=False, server_default="FALSE"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("body_templates")
