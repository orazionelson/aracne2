"""Add users.orcid — canonical ORCID identifier for an Aracne2 user.

Optional 19-char string (``XXXX-XXXX-XXXX-XXXX``; last char may be X
as ISO 7064 Mod 11-2 checksum). Powers Zenodo deposit
``creator.identifiers`` and LOD ``schema:sameAs`` edges when this
user is the editor of a published / deposited collection.

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("orcid", sa.String(length=19), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "orcid")
