"""Seed system_settings rows for the Zenodo deposit plugin (and public_base_url).

Adds rows used by the non-native ``zenodo_deposit`` plugin plus a
generic ``public_base_url`` used by any plugin that needs to emit URLs
outside of an HTTP request context. All rows are inserted with sensible
empty / disabled defaults so activating the plugin does not surprise
anyone with live deposits.

Revision ID: 0047
Revises: 0046
Create Date: 2026-04-22
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


_NEW_SETTINGS: list[tuple[str, str, str]] = [
    ("public_base_url", "", "string"),
    ("zenodo_api_token", "", "string"),
    ("zenodo_base_url", "https://sandbox.zenodo.org", "string"),
    ("zenodo_default_community", "", "string"),
    ("zenodo_auto_publish", "false", "bool"),
    ("zenodo_access_right", "open", "string"),
    ("zenodo_publication_type", "other", "string"),
]


def upgrade() -> None:
    for key, value, type_ in _NEW_SETTINGS:
        op.execute(
            f"""
            INSERT INTO system_settings (key, value, type)
            VALUES ('{key}', '{value}', '{type_}')
            ON CONFLICT (key) DO NOTHING;
            """
        )


def downgrade() -> None:
    keys = ",".join(f"'{k}'" for k, _, _ in _NEW_SETTINGS)
    op.execute(f"DELETE FROM system_settings WHERE key IN ({keys});")
