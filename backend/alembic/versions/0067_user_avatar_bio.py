"""Add ``avatar_url`` and ``bio`` to ``users``.

Two optional profile fields surfaced in the Profile page:

- ``avatar_url`` (``Text``, nullable): when set, identifies an
  uploaded image stored under ``media/avatars/<user_id>.<ext>``;
  served via a dedicated public endpoint. When unset, the UI falls
  back to a deterministic monogram avatar generated from the
  username + a hash-derived palette colour, so no choice is
  required from new users.
- ``bio`` (``Text``, nullable): a short freeform bio, visible only
  on the in-app profile page for now (no public exposure on
  generated websites yet — a follow-up will add the ``respStmt``
  surface). The frontend caps the input at 500 chars and accepts
  a tiny Markdown subset (``**bold**``, ``*italic*``,
  ``__underline__``).

Revision ID: 0067
Revises: 0066
Create Date: 2026-04-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bio")
    op.drop_column("users", "avatar_url")
