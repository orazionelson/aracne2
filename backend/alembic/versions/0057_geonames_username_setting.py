"""Seed the ``geonames_username`` system_setting.

Moves the GeoNames account name from a Pydantic Settings env var
(``geonames_username`` on ``Settings``, default ``"aracne"``) to the
``system_settings`` table, where an Admin can edit it from the admin
UI without a container restart. Same pattern as the CrossRef contact
email in migration 0055.

Default value stays ``"aracne"`` for backward compatibility — existing
deployments keep working as before. On boot the backend emits a
``geonames_using_shared_default`` warning so operators who look at
the logs are nudged to register their own free username at
https://www.geonames.org/login (the shared default is subject to a
20k-req/day quota and is against GeoNames' TOS to share across
applications).

Revision ID: 0057
Revises: 0056
Create Date: 2026-04-24
"""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('geonames_username', 'aracne', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'geonames_username';"
    )
