"""``continuity_plan`` — what happens to the corpus if the operator
disappears, the institution closes, or the funding ends.

Categories: ``cts:R3`` (Continuity of access). Heavy on operator
declarations; the platform contributes the active deposit list +
the OAI-PMH endpoint as evidence the corpus is replicated outward.
"""

from app.plugins.policy_pages.platform import (
    active_deposit_targets,
    plugin_active,
    system_setting,
)
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _oai_pmh_endpoint() -> str:
    base = system_setting("public_base_url", "")
    if not base:
        return "(not configured)"
    return f"{base.rstrip('/')}/oai-pmh"


def _backup_retention_summary() -> str:
    n = system_setting("backup_retention_count", "")
    return f"{n} most-recent snapshots" if n else "(default — see backup plugin config)"


TEMPLATE = PolicyTemplate(
    slug="continuity_plan",
    title_key="policy.continuity_plan.title",
    categories=("cts:R3",),
    fields=(
        Field("active_deposit_targets", "platform", source=active_deposit_targets,
              label_key="policy.continuity_plan.deposit_targets"),
        Field("oai_pmh_endpoint", "platform", source=_oai_pmh_endpoint,
              label_key="policy.continuity_plan.oai_pmh_endpoint"),
        Field("backup_retention", "platform", source=_backup_retention_summary,
              label_key="policy.continuity_plan.backup_retention"),
        Field("successor_institution", "textarea", required=True, localized=True,
              label_key="policy.continuity_plan.successor_institution",
              hint_key="policy.continuity_plan.successor_institution_hint"),
        Field("doi_redirection_procedure", "textarea", localized=True,
              label_key="policy.continuity_plan.doi_redirection_procedure"),
        Field("communication_plan", "textarea", required=True, localized=True,
              label_key="policy.continuity_plan.communication_plan"),
        Field("succession_horizon_years", "integer", min=1, max=100,
              label_key="policy.continuity_plan.succession_horizon_years"),
    ),
    public_template="_default.md.j2",
)
