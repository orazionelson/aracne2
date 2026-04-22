"""Add per-collection zenodo_resource_type override.

Lets an EditorInChief pick the InvenioRDM resource-type vocabulary id
for a specific collection (e.g. "publication-book" for a manuscript,
"dataset" for a reference corpus). NULL means "inherit from the global
zenodo_resource_type setting", which is the behaviour before this
migration so existing collections are unaffected.

Revision ID: 0049
Revises: 0048
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("zenodo_resource_type", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "zenodo_resource_type")
