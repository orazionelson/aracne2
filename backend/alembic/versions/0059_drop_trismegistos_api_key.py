"""Drop the now-unused ``trismegistos_api_key`` system setting.

The Trismegistos plugin was rebuilt as an ID resolver against
Trismegistos's public ``texrelations`` / ``georelations``
endpoints — none of which require authentication. The API-key row
seeded by migration 0058 is therefore dead weight; this migration
deletes it. The ``openalex_contact_email`` row from 0058 stays
untouched.

``downgrade()`` re-seeds an empty ``trismegistos_api_key`` row so a
``downgrade head`` → ``upgrade head`` round-trip is clean.

Revision ID: 0059
Revises: 0058
Create Date: 2026-04-24
"""

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM system_settings WHERE key = 'trismegistos_api_key';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('trismegistos_api_key', '', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )
