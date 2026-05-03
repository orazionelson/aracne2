"""``expert_directory`` — named experts who guide the corpus.

Categories: ``core``, ``cts:R6`` (Expert guidance). Pure operator
declaration — multi-row form for the experts the institution
relies on.
"""

from app.plugins.policy_pages.templates._base import Field, PolicyTemplate

TEMPLATE = PolicyTemplate(
    slug="expert_directory",
    title_key="policy.expert_directory.title",
    categories=("core", "cts:R6"),
    fields=(
        Field("experts", "rows", required=True,
              label_key="policy.expert_directory.experts",
              hint_key="policy.expert_directory.experts_hint",
              rows_fields=(
                  Field("name", "text", required=True,
                        label_key="policy.expert_directory.expert_name"),
                  Field("role", "text", required=True, localized=True,
                        label_key="policy.expert_directory.expert_role"),
                  Field("expertise_area", "text", required=True, localized=True,
                        label_key="policy.expert_directory.expert_expertise"),
                  Field("contact", "text",
                        label_key="policy.expert_directory.expert_contact"),
                  Field("orcid", "text",
                        label_key="policy.expert_directory.expert_orcid"),
              )),
        Field("review_cadence", "textarea", localized=True,
              label_key="policy.expert_directory.review_cadence"),
    ),
    public_template="_default.md.j2",
)
