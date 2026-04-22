"""Migrate Zenodo deposit settings to the InvenioRDM schema.

The plugin is switching from the legacy ``/api/deposit/depositions`` flow
to the new Zenodo (InvenioRDM) ``/api/records`` flow. The user-visible
settings change shape:

- ``zenodo_publication_type`` → ``zenodo_resource_type``
  Legacy values (``other``, ``article``, ``book``, ``section``,
  ``preprint``, ``thesis``, ``report``, ``conferencepaper``) are mapped
  to the corresponding InvenioRDM vocabulary ids (``publication-other``,
  ``publication-article``, …) so that an admin who configured the plugin
  under the legacy API does not have to re-pick a resource type.

- ``zenodo_access_right`` → ``zenodo_access``
  InvenioRDM's access model is binary (public / restricted) plus an
  optional embargo with an ``until`` date. The MVP exposes only the
  binary axis. Legacy ``embargoed`` and ``closed`` values are folded
  into ``restricted`` — the admin can re-open the record explicitly.

Revision ID: 0048
Revises: 0047
Create Date: 2026-04-23
"""

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


# Legacy publication_type → InvenioRDM vocabulary id
_PUB_TYPE_MAP: dict[str, str] = {
    "other": "publication-other",
    "article": "publication-article",
    "book": "publication-book",
    "section": "publication-section",
    "preprint": "publication-preprint",
    "thesis": "publication-thesis",
    "report": "publication-report",
    "conferencepaper": "publication-conferencepaper",
}

# Legacy access_right → InvenioRDM-simplified access
_ACCESS_MAP: dict[str, str] = {
    "open": "open",
    "embargoed": "restricted",
    "restricted": "restricted",
    "closed": "restricted",
}


def upgrade() -> None:
    # 1. Insert the new keys with sensible defaults if they do not exist yet.
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('zenodo_resource_type', 'publication-other', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('zenodo_access', 'open', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )

    # 2. Carry forward the user's previous selections, if any.
    for legacy_value, new_value in _PUB_TYPE_MAP.items():
        op.execute(
            f"""
            UPDATE system_settings
               SET value = '{new_value}', updated_at = NOW()
             WHERE key = 'zenodo_resource_type'
               AND EXISTS (
                   SELECT 1 FROM system_settings s
                    WHERE s.key = 'zenodo_publication_type'
                      AND s.value = '{legacy_value}'
               );
            """
        )
    for legacy_value, new_value in _ACCESS_MAP.items():
        op.execute(
            f"""
            UPDATE system_settings
               SET value = '{new_value}', updated_at = NOW()
             WHERE key = 'zenodo_access'
               AND EXISTS (
                   SELECT 1 FROM system_settings s
                    WHERE s.key = 'zenodo_access_right'
                      AND s.value = '{legacy_value}'
               );
            """
        )

    # 3. Drop the legacy keys.
    op.execute(
        "DELETE FROM system_settings WHERE key IN ('zenodo_publication_type', 'zenodo_access_right');"
    )


def downgrade() -> None:
    # Recreate the legacy rows with mapped defaults so a downgrade does not
    # leave the plugin without access/type keys.
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('zenodo_publication_type', 'other', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('zenodo_access_right', 'open', 'string')
        ON CONFLICT (key) DO NOTHING;
        """
    )

    # Reverse mapping of resource_type → legacy pub type (best-effort).
    reverse_pub: dict[str, str] = {v: k for k, v in _PUB_TYPE_MAP.items()}
    for new_value, legacy_value in reverse_pub.items():
        op.execute(
            f"""
            UPDATE system_settings
               SET value = '{legacy_value}', updated_at = NOW()
             WHERE key = 'zenodo_publication_type'
               AND EXISTS (
                   SELECT 1 FROM system_settings s
                    WHERE s.key = 'zenodo_resource_type'
                      AND s.value = '{new_value}'
               );
            """
        )

    op.execute(
        "DELETE FROM system_settings WHERE key IN ('zenodo_resource_type', 'zenodo_access');"
    )
