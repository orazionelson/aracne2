"""Codeberg plugin — per-website link table.

Symmetric to ``codeberg_collection_links`` (migration 0060) but scoped
to a Website. Adds ``last_push_file_count`` alongside the regular
last-push bookkeeping so the UI can say "Last push: 42 files" without
re-reading the rendered site tree.

Revision ID: 0061
Revises: 0060
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "codeberg_website_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "website_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("websites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "base_url",
            sa.String(256),
            nullable=False,
            server_default="https://codeberg.org",
        ),
        sa.Column("repo_owner", sa.String(128), nullable=False),
        sa.Column("repo_name", sa.String(128), nullable=False),
        sa.Column(
            "branch", sa.String(128), nullable=False, server_default="main",
        ),
        sa.Column("pat_override", sa.Text(), nullable=True),
        sa.Column("last_push_sha", sa.String(64), nullable=True),
        sa.Column(
            "last_push_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("last_push_file_count", sa.Integer(), nullable=True),
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
            "website_id", name="uq_codeberg_link_website",
        ),
    )


def downgrade() -> None:
    op.drop_table("codeberg_website_links")
