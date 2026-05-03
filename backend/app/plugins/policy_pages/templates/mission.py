"""``mission`` — institutional mission and scope.

Categories: ``core`` (every deployment), ``cts:R1`` (Mission/Scope).
Smallest of the 12 templates; just the operator's mission statement
plus a couple of pointers.
"""

from app.plugins.policy_pages.platform import aracne_version
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate

TEMPLATE = PolicyTemplate(
    slug="mission",
    title_key="policy.mission.title",
    categories=("core", "cts:R1"),
    fields=(
        Field("aracne_version", "platform", source=aracne_version,
              label_key="policy.platform.aracne_version"),
        Field("mission_statement", "textarea", required=True, localized=True,
              label_key="policy.mission.statement",
              hint_key="policy.mission.statement_hint"),
        Field("scope", "textarea", required=True, localized=True,
              label_key="policy.mission.scope"),
        Field("target_community", "textarea", required=True, localized=True,
              label_key="policy.mission.target_community"),
        Field("durability_commitment", "textarea", localized=True,
              label_key="policy.mission.durability_commitment"),
    ),
    public_template="_default.md.j2",
)
