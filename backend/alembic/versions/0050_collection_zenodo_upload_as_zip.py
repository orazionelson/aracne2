"""Add per-collection zenodo_upload_as_zip flag.

When true, the Zenodo deposit plugin bundles every TEI document in the
collection into a single ZIP archive named ``{slug}.zip`` and uploads
that one file, instead of PUT-ing each XML to its own file entry.
Default is false so existing collections keep their current behaviour.

Revision ID: 0050
Revises: 0049
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "zenodo_upload_as_zip",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "zenodo_upload_as_zip")
