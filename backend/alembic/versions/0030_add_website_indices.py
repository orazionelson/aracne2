"""Add website_indices table and tag-discovery cache to websites.

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tag-discovery cache to websites
    op.add_column("websites", sa.Column("distinct_tags", JSONB(), nullable=True))
    op.add_column(
        "websites",
        sa.Column("tags_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create website_indices table
    op.create_table(
        "website_indices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "website_id",
            UUID(as_uuid=True),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("tag", sa.String(128), nullable=False),
        sa.Column("key_attribute", sa.String(128), nullable=True),
        sa.Column("subkey_attribute", sa.String(128), nullable=True),
        sa.Column("cached_data", JSONB(), nullable=True),
        sa.Column("last_built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_website_indices_website_id", "website_indices", ["website_id"])
    op.create_unique_constraint(
        "uq_website_indices_website_label",
        "website_indices",
        ["website_id", "label"],
    )


def downgrade() -> None:
    op.drop_table("website_indices")
    op.drop_column("websites", "tags_refreshed_at")
    op.drop_column("websites", "distinct_tags")
