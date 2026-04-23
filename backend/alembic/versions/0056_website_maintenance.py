"""Add maintenance-mode columns to websites.

Introduces three new columns:

- ``maintenance_on_unpublish`` — when True, rendering of this website
  flips to a 503 maintenance banner as soon as the linked collection
  is unpublished. Default seeding respects the rendering mode:
    STATIC  → FALSE  (static site is a "release" and can outlive a
              transient unpublish of the source collection);
    DYNAMIC → TRUE   (dynamic rendering breaks without the collection
              being published — the banner is the humane fallback);
    HYBRID  → TRUE   (same reason for the dynamic half of the site).
- ``maintenance_message`` — optional custom banner text shown inside
  the 503 page. Falls back to an i18n default on the frontend.
- ``contact_email`` — optional per-website contact email displayed on
  the maintenance banner (and reusable by future surfaces, e.g. the
  public homepage footer). Falls back to the platform ``admin_email``
  when empty.

Revision ID: 0056
Revises: 0055
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "websites",
        sa.Column(
            "maintenance_on_unpublish",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "websites",
        sa.Column("maintenance_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "websites",
        sa.Column("contact_email", sa.String(length=256), nullable=True),
    )

    # Backfill defaults per rendering mode so existing DYNAMIC / HYBRID
    # sites immediately get the humane banner behaviour without manual
    # editing. STATIC sites keep the default FALSE set by the column.
    op.execute(
        """
        UPDATE websites
        SET maintenance_on_unpublish = TRUE
        WHERE rendering_mode IN ('DYNAMIC', 'HYBRID');
        """
    )

    # Drop the server_default now that the column is populated — the
    # ORM default (Python-side) is the authoritative source going
    # forward. Keeping the server_default would persist a Postgres
    # quirk into Alembic autogenerate runs.
    op.alter_column(
        "websites", "maintenance_on_unpublish", server_default=None,
    )


def downgrade() -> None:
    op.drop_column("websites", "contact_email")
    op.drop_column("websites", "maintenance_message")
    op.drop_column("websites", "maintenance_on_unpublish")
