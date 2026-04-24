"""Codeberg plugin — per-collection link table + global PAT setting.

Creates ``codeberg_collection_links`` (one link per collection binding
it to a Codeberg / self-hosted Forgejo repository) and seeds an empty
``codeberg_integration_pat`` row in ``system_settings`` for the
global PAT. The per-link ``pat_override`` column is Fernet-encrypted
when set (handled at the service layer, not the schema).

Revision ID: 0060
Revises: 0059
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "codeberg_collection_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
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
        sa.Column(
            "initialized_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("initialized_from_sha", sa.String(64), nullable=True),
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
            "collection_id", name="uq_codeberg_link_collection",
        ),
    )

    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('codeberg_integration_pat', '', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'codeberg_integration_pat';"
    )
    op.drop_table("codeberg_collection_links")
