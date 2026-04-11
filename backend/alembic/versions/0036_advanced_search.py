"""add advanced search fields to search_engines

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Feature flag: enable the advanced search page for this engine.
    op.add_column(
        "search_engines",
        sa.Column(
            "advanced_search_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # JSONB config storing named_tags and attribute_filters lists.
    op.add_column(
        "search_engines",
        sa.Column(
            "advanced_search_config",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("search_engines", "advanced_search_config")
    op.drop_column("search_engines", "advanced_search_enabled")
