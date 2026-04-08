"""add doc_count to collections

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-08
"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "doc_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "doc_count")
