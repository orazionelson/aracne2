"""GitHub plugin — per-collection + per-website link tables.

Symmetric with the Codeberg plugin (migrations 0060 / 0061):

- ``github_collection_links`` — one repo per collection; includes
  the same Initialize bookkeeping as its Codeberg sibling.
- ``github_website_links`` — one repo per website; push-only (no
  Initialize — websites are derived artefacts).

Also seeds the empty ``github_integration_pat`` row used by the
global plugin config. The per-link ``pat_override`` column is
Fernet-encrypted at rest via the shared ``SENSITIVE_KEYS`` path.

Revision ID: 0062
Revises: 0061
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_collection_links",
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
            server_default="https://github.com",
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
            "collection_id", name="uq_github_link_collection",
        ),
    )

    op.create_table(
        "github_website_links",
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
            server_default="https://github.com",
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
            "website_id", name="uq_github_link_website",
        ),
    )

    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('github_integration_pat', '', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'github_integration_pat';"
    )
    op.drop_table("github_website_links")
    op.drop_table("github_collection_links")
