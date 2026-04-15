"""add is_public to collection_bibliographies

Revision ID: 0045
Revises: 0044
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collection_bibliographies",
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "ix_collection_bibliographies_is_public",
        "collection_bibliographies",
        ["collection_id", "is_public"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_bibliographies_is_public",
        table_name="collection_bibliographies",
    )
    op.drop_column("collection_bibliographies", "is_public")
