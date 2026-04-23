"""Seed the ``crossref_contact_email`` system_setting.

Moves the CrossRef polite-pool identifier from a Pydantic Settings
env var (``crossref_contact_email`` on ``Settings``) to the
``system_settings`` table, where it sits alongside every other
plugin's runtime config and can be edited from the admin UI
without a container restart.

An empty value is fine — at lookup time the plugin falls back to the
platform's ``admin_email`` so freshly-activated installs still
identify themselves correctly to CrossRef.

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-23
"""

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('crossref_contact_email', '', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'crossref_contact_email';"
    )
