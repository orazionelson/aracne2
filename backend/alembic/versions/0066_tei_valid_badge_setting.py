"""Seed the ``public_tei_valid_badge_enabled`` system_settings row.

When true (the default), every public website whose backing
collection has a successful full-collection validation on record
renders a green "TEI valid" shield badge in its footer. The badge
carries ``id="tei-valid-badge"`` so deployments that want it hidden
or repositioned can do so with a short CSS rule in the site's
custom stylesheet — no core change required.

Turning the setting off hides the badge on every site at once,
useful for deployments that prefer to make no public claim about
validation status.

Revision ID: 0066
Revises: 0065
Create Date: 2026-04-24
"""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('public_tei_valid_badge_enabled', 'true', 'bool')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'public_tei_valid_badge_enabled';"
    )
