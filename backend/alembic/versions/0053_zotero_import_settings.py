"""Seed system_settings rows for the Zotero import plugin.

Adds four keys the non-native ``zotero_import`` plugin reads at
runtime: a read-only API key (Fernet-encrypted), the library type
(``user`` vs ``group``), the numeric library id, and an optional
override of the API base URL for tests or self-hosted mirrors.

Revision ID: 0053
Revises: 0052
Create Date: 2026-04-23
"""

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


_NEW_SETTINGS: list[tuple[str, str, str]] = [
    ("zotero_api_key", "", "string"),
    ("zotero_library_type", "group", "string"),
    ("zotero_library_id", "", "string"),
    ("zotero_api_base", "", "string"),
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
