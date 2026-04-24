"""Seed the settings rows used by the new authority-lookup plugins.

Inserts two idempotent rows into ``system_settings``:

- ``openalex_contact_email`` — non-sensitive string, empty default.
  Used by the OpenAlex plugin to enter the "polite pool" via a
  ``?mailto=…`` query param; falls back to ``admin_email`` when
  empty.
- ``trismegistos_api_key`` — sensitive (Fernet-encrypted at rest,
  added to ``SENSITIVE_KEYS`` in the same release). Empty default;
  the Trismegistos plugin returns HTTP 503 ``TMG_API_KEY_MISSING``
  until an Admin pastes a key obtained from
  https://www.trismegistos.org/api .

Same pattern as ``crossref_contact_email`` (0055) and
``geonames_username`` (0057).

Revision ID: 0058
Revises: 0057
Create Date: 2026-04-24
"""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('openalex_contact_email', '', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('trismegistos_api_key', '', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM system_settings
        WHERE key IN ('openalex_contact_email', 'trismegistos_api_key');
        """
    )
