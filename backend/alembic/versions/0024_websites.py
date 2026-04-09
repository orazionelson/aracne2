"""websites — static site management tables.

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-09

Adds:
  - website_rendering_mode enum (STATIC, DYNAMIC, HYBRID)
  - website_build_status enum (idle, pending, building, done, failed)
  - websites table
  - website_pages table
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types via DO blocks to handle re-runs safely.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE website_rendering_mode AS ENUM ('STATIC', 'DYNAMIC', 'HYBRID');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE website_build_status AS ENUM ('idle', 'pending', 'building', 'done', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "websites",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rendering_mode",
            ENUM(name="website_rendering_mode", create_type=False),
            nullable=False,
            server_default="STATIC",
        ),
        sa.Column(
            "theme_config",
            JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "nav_config",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "xslt_schema_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tei_schemas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "build_status",
            ENUM(name="website_build_status", create_type=False),
            nullable=False,
            server_default="idle",
        ),
        sa.Column("last_build_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("build_error", sa.Text(), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_websites_slug"),
    )
    op.create_index("ix_websites_collection_id", "websites", ["collection_id"])

    op.create_table(
        "website_pages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "website_id",
            UUID(as_uuid=True),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "website_id", "slug", name="uq_website_pages_website_slug"
        ),
    )
    op.create_index("ix_website_pages_website_id", "website_pages", ["website_id"])


def downgrade() -> None:
    op.drop_index("ix_website_pages_website_id", table_name="website_pages")
    op.drop_table("website_pages")
    op.drop_index("ix_websites_collection_id", table_name="websites")
    op.drop_table("websites")
    op.execute("DROP TYPE IF EXISTS website_build_status")
    op.execute("DROP TYPE IF EXISTS website_rendering_mode")
