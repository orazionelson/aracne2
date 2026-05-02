"""Add ``password_reset_tokens`` for the password recovery flow.

Phase EM-C of the email channels feature. The flow is:

1. ``POST /auth/password/reset/request {email_or_username}``
   generates a 256-bit random token, stores its SHA-256 digest in
   ``token_hash`` with ``expires_at = now() + 24h``, and emails the
   plaintext token to the user as part of a URL the frontend recognises.
2. ``POST /auth/password/reset/confirm {token, new_password}`` looks
   the row up by SHA-256, checks that ``used_at IS NULL`` and
   ``expires_at > now()``, applies the new password and revokes every
   active session of the user.

The plaintext token never lands in the DB — only the SHA-256 digest —
so a DB exfiltration cannot be used to reset accounts. ``ON DELETE
CASCADE`` on ``user_id`` ensures abandoned tokens disappear with their
user.

Revision ID: 0074
Revises: 0073
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
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
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # Lookup index: every confirm() walks ``token_hash`` so it must be
    # indexed; the unique constraint above already provides one but
    # we name it explicitly for downgrade clarity.
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_tokens_token_hash",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
