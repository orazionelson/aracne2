"""``preservation_plan`` — long-term preservation strategy.

Categories: ``cts:R10`` (Preservation plan). Platform contributes
TEI + schema list (format-as-preservation foundations); operator
declares the format-migration plan and the preservation horizon.
"""

from app.plugins.policy_pages.platform import (
    active_deposit_targets,
    schema_catalogue,
)
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _tei_format_in_use() -> str:
    return "TEI P5 (XML), schema-validated at deposit and on every public render"


TEMPLATE = PolicyTemplate(
    slug="preservation_plan",
    title_key="policy.preservation_plan.title",
    categories=("cts:R10",),
    fields=(
        Field("tei_format", "platform", source=_tei_format_in_use,
              label_key="policy.preservation_plan.tei_format"),
        Field("schema_catalogue", "platform", source=schema_catalogue,
              label_key="policy.preservation_plan.schema_catalogue"),
        Field("deposit_targets", "platform", source=active_deposit_targets,
              label_key="policy.preservation_plan.deposit_targets"),
        Field("preservation_horizon_years", "integer", required=True, min=1, max=200,
              label_key="policy.preservation_plan.preservation_horizon_years"),
        Field("format_migration_plan", "textarea", required=True, localized=True,
              label_key="policy.preservation_plan.format_migration_plan",
              hint_key="policy.preservation_plan.format_migration_plan_hint"),
        Field("format_normalisation_policy", "textarea", localized=True,
              label_key="policy.preservation_plan.format_normalisation_policy"),
        Field("media_policy", "textarea", localized=True,
              label_key="policy.preservation_plan.media_policy",
              hint_key="policy.preservation_plan.media_policy_hint"),
    ),
    public_template="_default.md.j2",
)
