"""Seed the system_settings rows used by the Dataverse Integration plugin.

The plugin has no per-link tables — per-deposit override of the
Dataverse alias travels in the request body and is recorded inside
the existing ``plugin_data`` payload. Only the global settings row
set needs an explicit migration.

The ``dataverse_api_token`` row is added to ``SENSITIVE_KEYS`` in
the same release so it is Fernet-encrypted at rest.

Revision ID: 0064
Revises: 0063
Create Date: 2026-04-24
"""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


_KEYS: list[tuple[str, str, str]] = [
    # (key, default value, type)
    ("dataverse_api_token", "", "string"),
    ("dataverse_base_url", "https://demo.dataverse.org", "string"),
    ("dataverse_default_alias", "", "string"),
    ("dataverse_auto_deposit", "false", "bool"),
    ("dataverse_auto_publish", "false", "bool"),
    ("dataverse_default_subject", "Arts and Humanities", "string"),
    ("dataverse_contact_name", "", "string"),
    ("dataverse_contact_email", "", "string"),
    ("dataverse_publish_type", "major", "string"),
]


def upgrade() -> None:
    for key, value, type_ in _KEYS:
        op.execute(
            f"""
            INSERT INTO system_settings (key, value, type)
            VALUES ('{key}', '{value}', '{type_}')
            ON CONFLICT (key) DO NOTHING;
            """
        )


def downgrade() -> None:
    keys_csv = ", ".join(f"'{k}'" for k, _, _ in _KEYS)
    op.execute(
        f"DELETE FROM system_settings WHERE key IN ({keys_csv});"
    )
