"""``funding_staffing`` — funding sources, staff, succession.

Categories: ``core``, ``cts:R5`` (Organizational infrastructure).
Pure operator declaration: no platform-introspected fields.
"""

from app.plugins.policy_pages.templates._base import Field, PolicyTemplate

TEMPLATE = PolicyTemplate(
    slug="funding_staffing",
    title_key="policy.funding_staffing.title",
    categories=("core", "cts:R5"),
    fields=(
        Field("funding_sources", "textarea", required=True, localized=True,
              label_key="policy.funding_staffing.funding_sources",
              hint_key="policy.funding_staffing.funding_sources_hint"),
        Field("staffing_roles", "rows", required=True,
              label_key="policy.funding_staffing.staffing_roles",
              rows_fields=(
                  Field("title", "text", required=True, localized=True,
                        label_key="policy.funding_staffing.staff_title"),
                  Field("incumbent", "text",
                        label_key="policy.funding_staffing.staff_incumbent"),
                  Field("contact", "text",
                        label_key="policy.funding_staffing.staff_contact"),
              )),
        Field("succession_arrangements", "textarea", required=True, localized=True,
              label_key="policy.funding_staffing.succession_arrangements"),
        Field("budget_horizon_years", "integer", min=1, max=50,
              label_key="policy.funding_staffing.budget_horizon_years"),
    ),
    public_template="_default.md.j2",
)
