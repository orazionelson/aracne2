"""Add collections table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enum type
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE collection_status AS ENUM (
                'draft', 'assigned', 'review', 'published'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 2. Table
    op.create_table(
        "collections",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            ENUM(name="collection_status", create_type=False),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("editor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["editor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # 3. Indexes
    op.create_index("ix_collections_slug", "collections", ["slug"])
    op.create_index("ix_collections_status", "collections", ["status"])
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"])
    op.create_index("ix_collections_editor_id", "collections", ["editor_id"])

    # 4. updated_at trigger — reuses fn_set_updated_at() from migration 0001
    op.execute("""
        CREATE TRIGGER trg_collections_updated_at
        BEFORE UPDATE ON collections
        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_collections_updated_at ON collections")
    op.drop_index("ix_collections_editor_id", table_name="collections")
    op.drop_index("ix_collections_owner_id", table_name="collections")
    op.drop_index("ix_collections_status", table_name="collections")
    op.drop_index("ix_collections_slug", table_name="collections")
    op.drop_table("collections")
    op.execute("DROP TYPE IF EXISTS collection_status")
