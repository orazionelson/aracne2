"""Add is_native column to plugins

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plugins",
        sa.Column(
            "is_native",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("plugins", "is_native")
