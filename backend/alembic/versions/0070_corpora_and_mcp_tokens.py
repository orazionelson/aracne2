"""Add ``corpora``, ``corpus_collections``, and ``mcp_tokens`` tables.

A *corpus* is a thematic grouping of public, published collections.
The MCP server uses it to scope a bearer token's read access to a
specific subset of collections, so an admin can hand "Editor1, your
token only sees the Shakespeare corpus" to one editor and a separate
token for the "Sommaria" corpus to another.

The schema is intentionally generic so future scoped features (search
engines limited to a corpus, sitemap subsections, scoped exports) can
attach to the same primitive.

Cascade rules:

* Deleting a corpus cascades through ``corpus_collections`` and revokes
  all tokens issued against it (``mcp_tokens.corpus_id`` ON DELETE
  CASCADE).
* Deleting a collection cascades through ``corpus_collections`` only —
  the corpus survives, just with one fewer collection.

``mcp_tokens.hashed_token`` stores a bcrypt digest of the urlsafe
random plaintext; the auth code bcrypt-checks incoming bearers
against every non-revoked row of the corpus.

Revision ID: 0070
Revises: 0069
Create Date: 2026-04-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpora",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "corpus_collections",
        sa.Column(
            "corpus_id",
            UUID(as_uuid=True),
            sa.ForeignKey("corpora.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "mcp_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "corpus_id",
            UUID(as_uuid=True),
            sa.ForeignKey("corpora.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("hashed_token", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_mcp_tokens_corpus_id",
        "mcp_tokens",
        ["corpus_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_tokens_corpus_id", table_name="mcp_tokens")
    op.drop_table("mcp_tokens")
    op.drop_table("corpus_collections")
    op.drop_table("corpora")
