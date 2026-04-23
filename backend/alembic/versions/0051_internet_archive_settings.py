"""Seed system_settings rows for the Internet Archive plugin.

Adds the three keys the non-native ``internet_archive`` plugin reads
at runtime: two Fernet-encrypted API keys (access + secret, from
https://archive.org/account/s3.php) and an ``auto_archive`` toggle
that decides whether publishing a collection automatically submits it
to Save Page Now.

Revision ID: 0051
Revises: 0050
Create Date: 2026-04-23
"""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


_NEW_SETTINGS: list[tuple[str, str, str]] = [
    ("internet_archive_access_key", "", "string"),
    ("internet_archive_secret_key", "", "string"),
    ("internet_archive_auto_archive", "true", "bool"),
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
