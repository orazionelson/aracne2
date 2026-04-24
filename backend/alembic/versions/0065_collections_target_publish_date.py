"""Add ``target_publish_date`` column to ``collections``.

Soft editorial target date set by the EiC to flag when a collection
is expected to be published. The workflow panel on the Collection
detail page renders a countdown badge based on this value (amber
when overdue, neutral otherwise). No backend enforcement — missing
the date does not block anything.

Nullable with no server default: unset collections keep NULL and
the frontend simply omits the badge. Every existing row becomes
NULL at migrate-in time; no backfill needed.

Revision ID: 0065
Revises: 0064
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("target_publish_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "target_publish_date")
