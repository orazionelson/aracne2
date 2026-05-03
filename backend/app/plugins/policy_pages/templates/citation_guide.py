"""``citation_guide`` — how readers should cite the corpus.

Categories: ``core``. Platform side reports whether DOI / JSON-LD
markup is enabled so the suggested citation can carry a DOI;
operator side supplies the citation format and attribution
expectations.
"""

from app.plugins.policy_pages.platform import plugin_active, system_setting
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


def _doi_badge_present() -> str:
    return (
        "Yes — Zenodo deposit plugin active"
        if plugin_active("zenodo")
        else "Not configured — corpus does not currently mint DOIs"
    )


def _jsonld_status() -> str:
    enabled = system_setting("public_search_engine_enabled", "false") == "true"
    return "Active on every public document page" if enabled else "Not currently enabled"


TEMPLATE = PolicyTemplate(
    slug="citation_guide",
    title_key="policy.citation_guide.title",
    categories=("core",),
    fields=(
        Field("doi_badge", "platform", source=_doi_badge_present,
              label_key="policy.citation_guide.doi_badge"),
        Field("jsonld_status", "platform", source=_jsonld_status,
              label_key="policy.citation_guide.jsonld_status"),
        Field("suggested_citation", "textarea", required=True, localized=True,
              label_key="policy.citation_guide.suggested_citation",
              hint_key="policy.citation_guide.suggested_citation_hint"),
        Field("attribution_expectations", "textarea", required=True, localized=True,
              label_key="policy.citation_guide.attribution_expectations"),
        Field("citation_examples", "textarea", localized=True,
              label_key="policy.citation_guide.citation_examples"),
    ),
    public_template="_default.md.j2",
)
