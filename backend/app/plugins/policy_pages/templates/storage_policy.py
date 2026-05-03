"""``storage_policy`` — operational storage and backup policy.

Categories: ``cts:R9`` (Documented storage procedures). Mostly
operator-supplied; the platform side states the engines in use.
"""

from app.plugins.policy_pages.platform import (
    existdb_version,
    plugin_active,
    postgres_version,
)
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _backup_plugin_status() -> str:
    return "active" if plugin_active("backup") else "inactive"


TEMPLATE = PolicyTemplate(
    slug="storage_policy",
    title_key="policy.storage_policy.title",
    categories=("cts:R9",),
    fields=(
        Field("postgres_version", "platform", source=postgres_version,
              label_key="policy.platform.postgres_version"),
        Field("existdb_version", "platform", source=existdb_version,
              label_key="policy.platform.existdb_version"),
        Field("backup_plugin_status", "platform", source=_backup_plugin_status,
              label_key="policy.storage_policy.backup_plugin_status"),
        Field("offsite_target", "text", required=True, localized=True,
              label_key="policy.storage_policy.offsite_target",
              hint_key="policy.storage_policy.offsite_target_hint"),
        Field("rpo_hours", "integer", required=True, min=1, max=168,
              label_key="policy.storage_policy.rpo_hours"),
        Field("rto_hours", "integer", required=True, min=1, max=720,
              label_key="policy.storage_policy.rto_hours"),
        Field("key_custodian", "text", required=True, localized=True,
              label_key="policy.storage_policy.key_custodian"),
        Field("restore_rehearsal_cadence", "enum", required=True,
              options=("monthly", "quarterly", "annually"),
              label_key="policy.storage_policy.restore_rehearsal_cadence"),
        Field("encryption_at_rest", "textarea", localized=True,
              label_key="policy.storage_policy.encryption_at_rest"),
    ),
    public_template="_default.md.j2",
)
