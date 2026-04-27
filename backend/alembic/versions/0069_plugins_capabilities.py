"""Add ``capabilities`` and ``ui_descriptor`` to ``plugins``.

Two JSONB columns that let a plugin declare *what UI surface it
should auto-populate*. The platform itself does not interpret the
values — they are a contract between the plugin's ``PluginMeta``
and the SPA, which reads them through ``/api/v1/plugins`` and
renders the matching toolbar / panel without anybody editing the
SPA.

The first capability the SPA recognises is ``inline_authority`` —
authority-lookup plugins (Wikidata, ORCID, ROR, …) tag themselves
with it so the TEI editor's toolbar auto-renders one button per
active plugin and the matching side panel on click. Future
capabilities will follow the same shape.

Both columns default to JSONB-empty so existing plugins keep
loading unchanged. The plugin loader's ``sync_registry`` rewrites
them on every boot from ``PluginMeta.capabilities`` /
``ui_descriptor``, so this migration only needs to add the columns.

Revision ID: 0069
Revises: 0068
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plugins",
        sa.Column(
            "capabilities",
            JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "plugins",
        sa.Column(
            "ui_descriptor",
            JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("plugins", "ui_descriptor")
    op.drop_column("plugins", "capabilities")
