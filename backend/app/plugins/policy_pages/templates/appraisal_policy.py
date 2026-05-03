"""``appraisal_policy`` — what gets accepted, what gets rejected,
and how a deposit is removed if necessary.

Categories: ``cts:R8`` (Appraisal). Platform shows the current
collection / schema state; operator declares the editorial
acceptance / rejection / deaccessioning rules.
"""

from app.plugins.policy_pages.platform import (
    published_collection_count,
    schema_catalogue,
)
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate

TEMPLATE = PolicyTemplate(
    slug="appraisal_policy",
    title_key="policy.appraisal_policy.title",
    categories=("cts:R8",),
    fields=(
        Field("published_count", "platform", source=published_collection_count,
              label_key="policy.appraisal_policy.published_count"),
        Field("schema_catalogue", "platform", source=schema_catalogue,
              label_key="policy.appraisal_policy.schema_catalogue"),
        Field("acceptance_criteria", "textarea", required=True, localized=True,
              label_key="policy.appraisal_policy.acceptance_criteria"),
        Field("rejection_criteria", "textarea", required=True, localized=True,
              label_key="policy.appraisal_policy.rejection_criteria"),
        Field("deaccessioning_procedure", "textarea", required=True, localized=True,
              label_key="policy.appraisal_policy.deaccessioning_procedure",
              hint_key="policy.appraisal_policy.deaccessioning_procedure_hint"),
        Field("editorial_review_cadence", "textarea", localized=True,
              label_key="policy.appraisal_policy.editorial_review_cadence"),
    ),
    public_template="_default.md.j2",
)
