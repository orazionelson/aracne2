"""Add ``personal_access_tokens`` for the headless CLI auth flow.

Phase CLI-A of the bulk import/export tool feature. Each Editor+ can
issue one or more long-lived bearer tokens from their profile and pass
them to the standalone ``aracne-cli`` so the CLI can call any REST
endpoint they could call from the SPA. Plaintext tokens are never
stored — only their bcrypt digest, mirroring the ``mcp_tokens``
pattern from migration 0070.

Cascade rules:

- ``user_id`` ON DELETE CASCADE so deleting a user wipes their tokens.

The label is required (the user names the token at issue time, e.g.
"my-laptop") so a token list is human-readable. ``revoked_at`` stamps a
soft delete; ``last_used_at`` is bumped by the auth dispatch every time
the token resolves successfully.

Revision ID: 0075
Revises: 0074
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_access_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
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
    )
    op.create_index(
        "ix_personal_access_tokens_user_id",
        "personal_access_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personal_access_tokens_user_id",
        table_name="personal_access_tokens",
    )
    op.drop_table("personal_access_tokens")
